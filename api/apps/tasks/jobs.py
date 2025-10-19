import asyncio
import random
import time
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar, Union, Dict

from apps.tasks.exceptions import TaskFailedError, TaskCancellableError
from apps.tasks.models.task_manager import ProgressInfoModel, TaskRecordModel


logger = logging.getLogger(__name__)


F = TypeVar("F", bound=Callable[[TaskRecordModel], Awaitable[Any]])


def with_simulated_duration(duration: int = 30, tick: float = 1.0) -> Callable[[F], F]:
    """
    Decorator for task actions:
    - Simulates a single continuous processing phase of `duration` seconds.
    - Emits progress based on *time remaining* (100 -> 0).
    - Handles cooperative cancellation via `rec.cancel_requested`.
    """
    def _decorator(fn: F) -> F:
        async def _wrapped(rec: TaskRecordModel, *args):
            total = max(1, int(duration))
            rec.est_total_seconds = total

            # anchors
            if rec.started_monotonic is None:
                rec.started_monotonic = time.monotonic()
            started_at_dt = datetime.now(timezone.utc)

            # initial: 100% remaining
            rec.info.progress = 100
            rec.info.progress_info = ProgressInfoModel(
                message="100% remaining",
                started_at=started_at_dt,
                eta_seconds=total,
            )
            rec.updated_at = datetime.now(timezone.utc)

            # tick loop
            while True:
                elapsed = int(time.monotonic() - rec.started_monotonic)
                remaining = max(0, total - elapsed)
                percent_completed = int(min(100, int(elapsed * 100 / total))) if total > 0 else 100
                percent_remaining = max(0, 100 - percent_completed)

                # cancellation
                if rec.cancel_requested:
                    rec.info.status = "cancelled"
                    rec.info.error = "Cancelled during processing"
                    rec.info.progress = percent_completed
                    rec.info.progress_info = ProgressInfoModel(
                        message="Cancelled on request",
                        started_at=started_at_dt,
                        eta_seconds=None,
                    )
                    rec.updated_at = datetime.now(timezone.utc)
                    rec.event.set()
                    raise TaskCancellableError("Task cancelled")

                # progress update (remaining)
                rec.info.progress = percent_completed
                rec.info.progress_info = ProgressInfoModel(
                    message=f"{percent_remaining}% remaining",
                    started_at=started_at_dt,
                    eta_seconds=remaining,
                )
                rec.updated_at = datetime.now(timezone.utc)

                if remaining <= 0:
                    break
                await asyncio.sleep(tick)

            # Execute the actual task logic (fast) after timing ends
            return await fn(*args, **rec.info.parameters)

        return _wrapped  # type: ignore[return-value]
    return _decorator


@with_simulated_duration(duration=30, tick=1.0)
async def compute_sum(*args, **kwargs) -> Union[int, float]:
    numbers = kwargs.get("numbers")
    if not isinstance(numbers, list) or not all(isinstance(n, (int, float)) for n in numbers):
        raise TaskFailedError("Invalid 'numbers' parameter; expected list of numbers.")
    return sum(numbers)


@with_simulated_duration(duration=25, tick=1.0)
async def generate_report(title: str, sections: dict, *args, **kwargs) -> str:
    return f"{title}: " + ", ".join(str(s) for s in sections)


@with_simulated_duration(duration=20, tick=1.0)
async def lucky_job(*args, **kwargs) -> Dict[str, Any]:
    if random.random() < 0.5:
        raise TaskFailedError("Unstable task failed randomly.")
    return {"ok": True}


@with_simulated_duration(duration=15, tick=1.0)
async def batch_email(*args, **kwargs) -> bool:
    emails = kwargs.get("emails")
    logger.info("Sending emails: %s", emails)
    # Example: simulate sending emails and possible transient failure
    if random.random() < 0.2:
        raise TaskFailedError("Email provider temporary failure.")
    return True
