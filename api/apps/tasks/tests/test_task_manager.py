import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from apps.tasks.exceptions import QueueFullError
from apps.tasks.models.task_manager import TaskInfoModel, TaskRecordModel
from apps.tasks.services.task_manager import TaskManager


@pytest.mark.asyncio
async def test_tasks_cleaned():
    """
    Test that tasks are cleaned up after a certain time when in completed,
    cancelled, or failed state.
    """
    # Arrange
    tm = TaskManager(cleanup_after_seconds=0, cleanup_sleep_seconds=0)
    now = datetime.now(timezone.utc) - timedelta(seconds=1)

    tfm = TaskInfoModel(
        task_id=uuid4(),
        status='completed',
        task_type='batch_email',
        parameters={'emails': ['test1@test.com']},
    )
    tm.tasks[tfm.task_id] = TaskRecordModel(
        info=tfm,
        created_at=now,
        updated_at=now,
    )

    tfm = TaskInfoModel(
        task_id=uuid4(),
        status='cancelled',
        task_type='batch_email',
        parameters={'emails': ['test1@test.com']},
    )
    tm.tasks[tfm.task_id] = TaskRecordModel(
        info=tfm,
        created_at=now,
        updated_at=now,
    )

    tfm = TaskInfoModel(
        task_id=uuid4(),
        status='failed',
        task_type='batch_email',
        parameters={'emails': ['test1@test.com']},
    )
    tm.tasks[tfm.task_id] = TaskRecordModel(
        info=tfm,
        created_at=now,
        updated_at=now,
    )

    assert len(tm.tasks) == 3

    # Act
    async def wait_until_tasks_empty(
        tman: TaskManager,
        timeout: float = 1.0,
        poll: float = 0.01,
    ) -> None:
        async def _wait() -> None:
            while True:
                async with tman._lock:  # be consistent with TaskManager mutations
                    if not tman.tasks:
                        return
                await asyncio.sleep(poll)

        await asyncio.wait_for(_wait(), timeout=timeout)

    await tm.start()
    await wait_until_tasks_empty(tm, timeout=1.0, poll=0.01)

    # Assert
    assert len(tm.tasks) == 0
    await tm.stop()


@pytest.mark.asyncio
async def test_task_manager_max_queue_size():
    """
    Without starting workers, the queue won't be drained. Filling it to
    capacity should raise QueueFullError on the next submit().
    """
    tm = TaskManager(
        max_queue_size=5,
        concurrency=1,
    )

    # First submit succeeds
    await tm.submit('any', {'n': 1}, priority=0)

    # Second submit should raise
    with pytest.raises(QueueFullError):
        coroutines = []
        for _ in range(5):
            coroutines.append(
                tm.submit(
                    'generate_report',
                    {
                        'title': 'Monthly Report',
                        'sections': ['overview', 'details', 'summary'],
                    },
                    priority=0,
                )
            )
        await asyncio.gather(*coroutines)


@pytest.mark.asyncio
@pytest.mark.timeout(3)
async def test_task_manager_concurrency(monkeypatch):
    """
    Verify tasks are processed concurrently by timing N tasks that each take
    ~0.2s. With concurrency=3 and 6 tasks, wall time should be ≈2 waves
    => ≈0.4s (allow slack).
    """
    tm = TaskManager(
        max_queue_size=100,
        concurrency=3,
        cleanup_after_seconds=60,
    )

    # Patch just this class' _process coroutine to simulate ~0.2s per task
    async def slow_process(self, rec):
        await asyncio.sleep(0.2)
        return 'ok'

    # If _process exists on the class, raising=True is fine.
    monkeypatch.setattr(TaskManager, '_process', slow_process, raising=True)

    await tm.start()
    try:
        # Enqueue 6 tasks (two "waves" at concurrency=3)
        for _ in range(6):
            await tm.submit(
                'generate_report',
                {
                    'title': 'Monthly Report',
                    'sections': ['overview', 'details', 'summary'],
                },
                priority=0,
            )

        # Give the workers a tick to start pulling from the queue before timing
        await asyncio.sleep(0)

        t0 = time.perf_counter()
        # Wait until workers have processed all queued items
        await tm.queue.join()
        dt = time.perf_counter() - t0

        # Expect about 0.4s (two waves at ~0.2s). Allow bounds for CI jitter.
        assert 0.2 <= dt < 0.9, (
            f'Expected ~0.4s with concurrency=3; got {dt:.3f}s'
        )
    finally:
        await tm.stop()


@pytest.mark.asyncio
async def test_priority_queue_internal_ordering():
    """
    Verify that the PriorityQueue orders by (priority ASC, seq ASC).
    We don't start workers; we just inspect enqueued tuples.
    """
    tm = TaskManager(max_queue_size=10, concurrency=0)

    # Enqueue: low priority first (higher number), then high priority
    info_low = await tm.submit('any', {'label': 'low-first'}, priority=10)
    info_high = await tm.submit('any', {'label': 'high-second'}, priority=0)

    # Pop in queue order
    first = tm.queue.get_nowait()   # (prio, seq, task_id)
    second = tm.queue.get_nowait()

    # Priority should make the (priority=0) item come out first
    assert first[0] == 0 and second[0] == 10

    # Map task_id back to the record to verify labels
    rec_first = await tm.get(first[2])
    rec_second = await tm.get(second[2])

    assert rec_first.info.parameters['label'] == 'high-second'
    assert rec_second.info.parameters['label'] == 'low-first'

    # Mark them done so queue.join() wouldn't hang if used
    tm.queue.task_done()
    tm.queue.task_done()


@pytest.mark.asyncio
async def test_priority_with_workers_order(monkeypatch):
    """
    Lower numeric priority should run earlier even if submitted later.
    """
    tm = TaskManager(
        max_queue_size=10,
        concurrency=1,
        cleanup_after_seconds=999,
        cleanup_sleep_seconds=0.05,
    )
    order: list[str] = []

    async def record_process(self, rec):
        order.append(rec.info.parameters['label'])
        await asyncio.sleep(0.01)
        return 'ok'

    async def _wait_for_queue_drained(
        tms: TaskManager,
        timeout: float = 2.0,
    ) -> None:
        """Await until queue is drained or timeout."""
        try:
            await asyncio.wait_for(tms.queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            pytest.fail('queue.join() timed out')

    # Patch on the CLASS so it binds (self, rec) correctly
    monkeypatch.setattr(TaskManager, '_process', record_process)

    await tm.start()
    try:
        await tm.submit('any', {'label': 'low-first'}, priority=10)
        await tm.submit('any', {'label': 'high-second'}, priority=0)

        await _wait_for_queue_drained(tm)
        assert order == ['high-second', 'low-first']
    finally:
        await tm.stop()


@pytest.mark.asyncio
async def test_cancel_when_queued_immediate():
    """
    Cancelling a queued task flips it to 'cancelled' immediately.
    """
    tm = TaskManager(max_queue_size=10, concurrency=0)
    info = await tm.submit('any', {'x': 1}, priority=5)
    cancelled = await tm.cancel(info.task_id)
    assert cancelled.status == 'cancelled'
    assert cancelled.error == 'Cancelled before processing'
