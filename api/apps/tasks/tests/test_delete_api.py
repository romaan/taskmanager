import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.tasks.api import router as tasks_router
from apps.tasks.depends.rate_limit import enforce_rate_limit
from apps.tasks.models.task_manager import TaskInfoModel, TaskRecordModel
from apps.tasks.services.task_manager import (
    TaskManager,
    TaskNotCancellableError,
)
from main import setup_exceptions


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(tasks_router)
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    setup_exceptions(app)
    return TestClient(app)


# -------------------------------
# DELETE: error cases
# -------------------------------


@pytest.mark.asyncio
async def test_cancel_task_invalid_uuid(client):
    tm = TaskManager()
    task_id = uuid4()

    tm.cancel = AsyncMock(return_value=None)

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        resp = client.delete('/api/v1/tasks/not-a-uuid')

    assert resp.status_code == 404
    assert resp.json() == {
        'code': 'not_found',
        'details': None,
        'message': 'Task not found',
        'request_id': None,
    }
    tm.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_task_not_found(client):
    tm = TaskManager()
    tid = uuid4()

    tm.cancel = AsyncMock(return_value=None)

    # cancel() returns None -> 404 "Task not found"
    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        resp = client.delete(f'/api/v1/tasks/{tid}')

    assert resp.status_code == 404, resp.text
    assert resp.json() == {
        'code': 'not_found',
        'details': None,
        'message': 'Task not found',
        'request_id': None,
    }
    tm.cancel.assert_awaited_once_with(tid)


@pytest.mark.asyncio
async def test_cancel_task_not_cancellable(client):
    tm = TaskManager()
    tid = uuid4()

    with patch('apps.tasks.api.get_task_manager', return_value=tm), patch.object(
        tm,
        'cancel',
        side_effect=TaskNotCancellableError('Already finished'),
    ):
        resp = client.delete(f'/api/v1/tasks/{tid}')

    assert resp.status_code == 404
    # Your exception handler maps detail into "message"
    assert resp.json() == {
        'code': 'not_found',
        'details': None,
        'message': 'Already finished',
        'request_id': None,
    }


@pytest.mark.asyncio
async def test_cancel_task_queued_immediate_200(client):
    """
    Queued task -> cancel immediately: 200 and status NOT "processing".
    """
    tm = TaskManager()
    tid = uuid4()
    now = datetime.now(timezone.utc)
    info_after = TaskInfoModel(
        task_id=tid,
        status='cancelled',
        task_type='batch_email',
        parameters={'emails': ['a@test.com']},
    )

    # Seed the task so waiting logic (if used) can find it
    tm.tasks[tid] = TaskRecordModel(
        info=TaskInfoModel(
            task_id=tid,
            status='queued',
            task_type='batch_email',
            parameters={'emails': ['a@test.com']},
        ),
        created_at=now,
        updated_at=now,
    )

    with patch('apps.tasks.api.get_task_manager', return_value=tm), patch.object(
        tm,
        'cancel',
        return_value=info_after,
    ):
        resp = client.delete(f'/api/v1/tasks/{tid}')

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['task_id'] == str(tid)
    assert body['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_cancel_task_processing_202_no_wait(client):
    """
    Processing task -> cancellation requested: returns 202 when not waiting.
    """
    tm = TaskManager()
    tid = uuid4()
    now = datetime.now(timezone.utc)

    # Seed as processing so the handler can set 202
    tm.tasks[tid] = TaskRecordModel(
        info=TaskInfoModel(
            task_id=tid,
            status='processing',
            task_type='generate_report',
            parameters={
                'title': 'Monthly Report',
                'sections': ['overview', 'details', 'summary'],
            },
        ),
        created_at=now,
        updated_at=now,
    )

    # cancel() returns current info indicating cancellation requested but still processing
    info_after = TaskInfoModel(
        task_id=tid,
        status='processing',
        task_type='generate_report',
        parameters={
            'title': 'Monthly Report',
            'sections': ['overview', 'details', 'summary'],
        },
    )

    with patch('apps.tasks.api.get_task_manager', return_value=tm), patch.object(
        tm,
        'cancel',
        return_value=info_after,
    ):
        resp = client.delete(f'/api/v1/tasks/{tid}')

    assert resp.status_code == 202, resp.text
    assert resp.json()['status'] == 'processing'


@pytest.mark.asyncio
async def test_cancel_task_processing_wait_transitions_to_cancelled_200(client):
    """
    With wait=true: initially processing (202), event flips to cancelled within
    timeout -> 200 and 'cancelled'.
    """
    tm = TaskManager()
    tid = uuid4()
    delay = 1.0
    timeout = 5

    # Seed record with processing status and an event
    with patch(
        'apps.tasks.services.task_manager.TaskManager._generate_uuid',
        return_value=tid,
    ):
        await tm.submit(
            'generate_report',
            {
                'title': 'Monthly Report',
                'sections': ['overview', 'details', 'summary'],
            },
            priority=0,
        )

    await tm.start()

    # cancel() returns processing immediately (request accepted)
    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        start = perf_counter()
        resp = client.delete(f'/api/v1/tasks/{tid}?wait=true&timeout={timeout}')
        elapsed = perf_counter() - start

    await asyncio.sleep(0.5)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['task_id'] == str(tid)
    assert body['status'] == 'cancelled'
    # Should wait at least ~delay, but far less than timeout
    assert elapsed >= delay - 0.05, f'elapsed={elapsed:.3f}s < delay~{delay}s'


@pytest.mark.asyncio
async def test_cancel_task_processing_wait_timeout_keeps_202(client):
    """
    With wait=true but no state change within timeout -> keep 202 and
    'processing'; ensure it waited ~timeout.
    """
    tm = TaskManager()
    tid = uuid4()
    now = datetime.now(timezone.utc)
    timeout = 3

    # Seed as processing; don't set the event within timeout
    rec = TaskRecordModel(
        info=TaskInfoModel(
            task_id=tid,
            status='processing',
            task_type='generate_report',
            parameters={},
        ),
        created_at=now,
        updated_at=now,
    )
    tm.tasks[tid] = rec

    info_after = rec.info  # cancel() reports still processing
    with patch('apps.tasks.api.get_task_manager', return_value=tm), patch.object(
        tm,
        'cancel',
        return_value=info_after,
    ):
        start = perf_counter()
        resp = client.delete(f'/api/v1/tasks/{tid}?wait=true&timeout={timeout}')
        elapsed = perf_counter() - start

    # No event.set() occurred; endpoint should time out and keep status 202
    assert resp.status_code == 202, resp.text
    assert resp.json()['status'] == 'processing'
    # Lower-bound with a small tolerance to avoid CI flakiness
    assert elapsed >= timeout - 0.25, (
        f'elapsed={elapsed:.3f}s < expected ~{timeout}s'
    )
