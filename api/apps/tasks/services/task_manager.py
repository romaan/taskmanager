import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID, uuid4

from apps.tasks.exceptions import (
    QueueFullError,
    TaskCancellableError,
    TaskFailedError,
    TaskNotCancellableError,
)
from apps.tasks.jobs import batch_email, compute_sum, generate_report, lucky_job
from apps.tasks.models.task_manager import (
    ProgressInfoModel,
    TaskInfoModel,
    TaskRecordModel,
)

logger = logging.getLogger(__name__)

# Priority queue item: lower priority runs earlier; seq keeps FIFO within same
# priority.
PQItem = Tuple[int, int, UUID]


class TaskManager:
    def __init__(
        self,
        max_queue_size: int = 100,
        concurrency: int = 5,
        cleanup_after_seconds: int = 60,
        cleanup_sleep_seconds: float = 0.5,
    ) -> None:
        self.queue: asyncio.PriorityQueue[PQItem] = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self.tasks: Dict[UUID, TaskRecordModel] = {}
        self.concurrency = concurrency
        self.cleanup_after_seconds = cleanup_after_seconds
        self.cleanup_sleep_seconds = cleanup_sleep_seconds
        self._workers: list[asyncio.Task] = []
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._seq = 0  # FIFO tiebreaker within same priority

    @staticmethod
    def _generate_uuid() -> UUID:
        return uuid4()

    async def start(self) -> None:
        """
        Start the workers and cleanup task.
        """
        logger.info("Starting %d workers", self.concurrency)
        for i in range(self.concurrency):
            self._workers.append(asyncio.create_task(self._worker(i)))
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """
        Stop the workers and cleanup task.
        """
        for w in self._workers:
            w.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        if self._cleanup_task:
            try:
                await self._cleanup_task
            except Exception:
                pass

    async def submit(
        self,
        task_type: str,
        parameters: Dict[str, Any],
        priority: int = 0,
    ) -> TaskInfoModel:
        """
        Submit a task to the queue. It will be picked up by a worker; put the
        task in "queued" status.
        """
        task_id = self._generate_uuid()
        info = TaskInfoModel(
            task_id=task_id,
            status="queued",
            task_type=task_type,
            parameters=parameters,
            progress=0,
            progress_info=ProgressInfoModel(
                message="Queued", started_at=None, eta_seconds=None
            ),
        )
        now = datetime.now(timezone.utc)
        record = TaskRecordModel(
            info=info,
            created_at=now,
            updated_at=now,
        )

        # Exclusively lock
        async with self._lock:
            self.tasks[task_id] = record
            self._seq += 1
            seq = self._seq

        try:
            # Lower priority number gets dequeued earlier; seq preserves submission
            # order within same priority.
            self.queue.put_nowait((priority, seq, task_id))
        except asyncio.QueueFull as e:
            async with self._lock:
                self.tasks.pop(task_id, None)
            raise QueueFullError(
                f"Task queue is full (max {self.queue.maxsize})"
            ) from e
        return info

    async def get(self, task_id: UUID) -> Optional[TaskRecordModel]:
        """
        Get the task record by its UUID or return None if not found.
        """
        async with self._lock:
            return self.tasks.get(task_id)

    async def cancel(self, task_id: UUID) -> Optional[TaskInfoModel]:
        """
        Cancel a task. If the task is already terminal, raise an error.
        """
        async with self._lock:
            rec = self.tasks.get(task_id)
            if not rec:
                return None

            # If task is already terminal, raise an error (caller will map to 404)
            if rec.info.status in ("completed", "failed", "cancelled"):
                raise TaskNotCancellableError(
                    f"Task {task_id} is already {rec.info.status}"
                )

            rec.cancel_requested = True

            if rec.info.status == "queued":
                # Cancel immediately
                rec.info.status = "cancelled"
                rec.info.error = "Cancelled before processing"
                rec.updated_at = datetime.now(timezone.utc)
                rec.event.set()
                return rec.info

            # Processing state; rec.cancel_requested=True and worker will honor it.
            rec.updated_at = datetime.now(timezone.utc)
            rec.event.set()
            return rec.info

    async def _worker(self, worker_index: int) -> None:
        logger.info("Worker %s started", worker_index)
        try:
            while True:
                # priority, seq, id
                _prio, _seq, task_id = await self.queue.get()
                rec = await self.get(task_id)
                if rec is None:
                    self.queue.task_done()
                    continue
                if rec.info.status == "cancelled":
                    self.queue.task_done()
                    continue

                # move to processing
                rec.info.status = "processing"
                rec.started_monotonic = time.monotonic()
                now_dt = datetime.now(timezone.utc)
                rec.updated_at = now_dt
                rec.info.progress = 0
                rec.info.progress_info = ProgressInfoModel(
                    message="Processing...",
                    started_at=now_dt,
                    eta_seconds=None,
                )
                rec.event.set()

                try:
                    result = await self._process(rec)
                    rec.info.status = "completed"
                    rec.info.result = result
                    rec.info.progress = 100
                    rec.info.progress_info = (
                        rec.info.progress_info
                        or ProgressInfoModel(
                            message="", started_at=now_dt, eta_seconds=None
                        )
                    ).model_copy(
                        update={"message": "Done", "eta_seconds": 0}
                    )
                except (asyncio.CancelledError, TaskCancellableError):
                    rec.info.status = "cancelled"
                except TaskFailedError as e:
                    rec.info.status = "failed"
                    rec.info.error = str(e)
                except Exception as e:  # noqa: BLE001 - keep broad catch for worker
                    logger.exception(
                        "Unexpected error processing task %s", task_id
                    )
                    rec.info.status = "failed"
                    rec.info.error = f"Unexpected error: {e}"
                finally:
                    rec.updated_at = datetime.now(timezone.utc)
                    rec.event.clear()
                    self.queue.task_done()
        except asyncio.CancelledError:
            logger.info("Worker %s cancelled", worker_index)
            return
        except Exception:
            logger.exception("Unexpected error in worker %s", worker_index)
            return

    async def _process(self, rec: TaskRecordModel) -> Any:
        """
        Dispatch to a task-type-specific method.
        Decorator simulates time + progress.
        """
        match rec.info.task_type:
            case "compute_sum":
                return await compute_sum(rec)
            case "generate_report":
                return await generate_report(rec)
            case "lucky_job":
                return await lucky_job(rec)
            case "batch_email":
                return await batch_email(rec)
        return None

    async def _cleanup_loop(self) -> None:
        logger.info("Cleanup started")
        try:
            while True:
                await asyncio.sleep(self.cleanup_sleep_seconds)
                now = datetime.now(timezone.utc)
                to_delete: list[UUID] = []
                async with self._lock:
                    for tid, rec in list(self.tasks.items()):
                        if rec.info.status in ("completed", "failed", "cancelled"):
                            age = (now - rec.updated_at).total_seconds()
                            if age >= self.cleanup_after_seconds:
                                to_delete.append(tid)
                    for tid in to_delete:
                        self.tasks.pop(tid, None)
                if to_delete:
                    logger.info("Cleaned up %d tasks", len(to_delete))
        except asyncio.CancelledError:
            return
