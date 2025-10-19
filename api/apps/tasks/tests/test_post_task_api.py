from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.tasks.api import router as tasks_router
from apps.tasks.depends.rate_limit import enforce_rate_limit
from apps.tasks.exceptions import QueueFullError
from apps.tasks.models.task_manager import TaskInfoModel
from apps.tasks.services.task_manager import TaskManager
from main import setup_exceptions


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(tasks_router)
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    setup_exceptions(app)
    return TestClient(app)


@pytest.mark.asyncio
async def test_post_batch_email_task_accepted(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='batch_email',
        parameters={'emails': ['abc@abc.com']},
    )
    tm.submit = AsyncMock(return_value=fake_info)
    payload = {
        'task_type': 'batch_email',
        'parameters': {'emails': ['test@example.com', 'abc@abc.com']},
        'priority': 1,
    }
    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 202
    assert response.json() == {'task_id': str(task_id), 'status': 'queued'}
    tm.submit.assert_awaited_once_with(
        'batch_email',
        {'emails': ['test@example.com', 'abc@abc.com']},
        priority=1,
    )


@pytest.mark.asyncio
async def test_post_compute_sum_task_accepted(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='compute_sum',
        parameters={'numbers': [1, 2, 3]},
    )
    tm.submit = AsyncMock(return_value=fake_info)
    payload = {
        'task_type': 'compute_sum',
        'parameters': {'numbers': [1, 2, 3]},
        'priority': 1,
    }
    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 202
    assert response.json() == {'task_id': str(task_id), 'status': 'queued'}
    tm.submit.assert_awaited_once_with(
        'compute_sum',
        {'numbers': [1, 2, 3]},
        priority=1,
    )


@pytest.mark.asyncio
async def test_post_generate_report_accepted(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='compute_sum',
        parameters={'numbers': [1, 2, 3]},
    )
    tm.submit = AsyncMock(return_value=fake_info)
    payload = {
        'task_type': 'generate_report',
        'parameters': {
            'title': 'Monthly Report',
            'sections': ['overview', 'details', 'summary'],
        },
    }
    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 202
    assert response.json() == {'task_id': str(task_id), 'status': 'queued'}
    tm.submit.assert_awaited_once_with(
        'generate_report',
        {
            'title': 'Monthly Report',
            'sections': ['overview', 'details', 'summary'],
        },
        priority=0,
    )


@pytest.mark.asyncio
async def test_post_lucky_job_accepted(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='compute_sum',
        parameters={'numbers': [1, 2, 3]},
    )
    tm.submit = AsyncMock(return_value=fake_info)

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        payload = {
            'task_type': 'lucky_job',
            'parameters': {},
        }
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 202
    assert response.json() == {'task_id': str(task_id), 'status': 'queued'}
    tm.submit.assert_awaited_once_with('lucky_job', {}, priority=0)


@pytest.mark.asyncio
async def test_post_compute_sum_missing_numbers_400(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='batch_email',
        parameters={'emails': ['abc@abc.com']},
    )
    tm.submit = AsyncMock(return_value=fake_info)

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        payload = {'task_type': 'compute_sum', 'parameters': {}}
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 400, response.text
    body = response.json()
    # Support either {"detail": [...]} or {"details": [...]}
    errors = body.get('detail')
    if errors is None:
        errors = body.get('details', [])
    assert isinstance(errors, list) and errors, f'Unexpected error body: {body}'

    # Accept both shapes: 'parameters/numbers' OR top-level 'numbers'
    saw_numbers = False
    for e in errors:
        loc = e.get('loc', [])
        path = '/'.join(map(str, loc)).lower()
        if (
            'parameters/numbers' in path
            or path.endswith('/numbers')
            or path == 'numbers'
        ):
            saw_numbers = True
            break
    assert saw_numbers, (
        f"Expected 'parameters/numbers' or 'numbers' in error locs, got: {errors}"
    )

    # type/message should indicate missing/required
    types = ' '.join(str(e.get('type', '')) for e in errors).lower()
    msgs = ' '.join(str(e.get('msg', '')) for e in errors).lower()
    assert (
        'missing' in types
        or 'required' in msgs
        or 'field required' in msgs
    ), errors

    tm.submit.assert_not_called()


@pytest.mark.asyncio
async def test_post_compute_sum_extra_key_forbidden_400(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='batch_email',
        parameters={'emails': ['abc@abc.com']},
    )
    tm.submit = AsyncMock(return_value=fake_info)

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        payload = {
            'task_type': 'compute_sum',
            'parameters': {'numbers': [1, 2], 'foo': 123},
        }
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 400, response.text
    body = response.json()
    # Support either {"detail": [...]} or {"details": [...]}
    errors = body.get('detail')
    if errors is None:
        errors = body.get('details', [])
    assert isinstance(errors, list) and errors, f'Unexpected error body: {body}'
    assert body.get('details')[0]['msg'] == 'Extra inputs are not permitted'
    assert response, (
        f"Expected 'parameters/numbers' or 'numbers' in error locs, got: {errors}"
    )

    tm.submit.assert_not_called()


@pytest.mark.asyncio
async def test_post_unsupported_task_type_400(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='batch_email',
        parameters={'emails': ['abc@abc.com']},
    )
    tm.submit = AsyncMock(return_value=fake_info)

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        payload = {
            'task_type': 'not_supported',
            'parameters': {'anything': True},
        }
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 400, response.text
    body = response.json()

    errors = body.get('detail')
    if errors is None:
        errors = body.get('details', [])
    assert isinstance(errors, list) and errors, f'Unexpected error body: {body}'

    # loc should reference task_type
    saw_task_type = False
    for e in errors:
        loc = e.get('loc', [])
        path = '/'.join(map(str, loc)).lower()
        if 'task_type' in path:
            saw_task_type = True
            break
    assert saw_task_type, f"'task_type' not found in error locs: {errors}"

    # type/message typically mention literal/enum mismatch
    types = ' '.join(str(e.get('type', '')) for e in errors).lower()
    msgs = ' '.join(str(e.get('msg', '')) for e in errors).lower()
    assert (
        'literal' in types
        or 'enum' in types
        or 'literal' in msgs
        or 'enum' in msgs
    ), errors

    tm.submit.assert_not_called()


@pytest.mark.asyncio
async def test_post_missing_parameters_400(client):
    # Arrange
    tm = TaskManager()
    task_id = uuid4()
    fake_info = TaskInfoModel(
        task_id=task_id,
        status='queued',
        task_type='batch_email',
        parameters={'emails': ['abc@abc.com']},
    )
    tm.submit = AsyncMock(return_value=fake_info)

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        payload = {'task_type': 'compute_sum'}  # no parameters provided
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 400, response.text
    body = response.json()
    errors = body.get('detail')
    if errors is None:
        errors = body.get('details', [])
    assert isinstance(errors, list) and errors, f'Unexpected error body: {body}'

    saw_expected_loc = False
    for e in errors:
        loc = e.get('loc', [])
        path = '/'.join(map(str, loc)).lower()
        # accept either nested (parameters) or flat (numbers) schema
        if 'parameters' in path or 'numbers' in path:
            saw_expected_loc = True
            break
    assert saw_expected_loc, (
        f"Expected 'parameters' or 'numbers' in error locs, got: {errors}"
    )

    types = ' '.join(str(e.get('type', '')) for e in errors).lower()
    msgs = ' '.join(str(e.get('msg', '')) for e in errors).lower()
    assert (
        'missing' in types
        or 'required' in msgs
        or 'field required' in msgs
    ), errors

    tm.submit.assert_not_called()


@pytest.mark.asyncio
async def test_post_task_queue_full_503(client):
    # Arrange
    tm = TaskManager()
    tm.submit = AsyncMock(side_effect=QueueFullError('Queue is full'))
    payload = {
        'task_type': 'batch_email',
        'parameters': {'emails': ['test@example.com']},
        'priority': 1,
    }

    with patch('apps.tasks.api.get_task_manager', return_value=tm):
        # Act
        response = client.post('/api/v1/tasks', json=payload)

    # Assert
    assert response.status_code == 503
    body = response.json()
    assert body == {
        'code': 'http_error',
        'details': None,
        'message': 'Task queue is full. Try again later.',
        'request_id': None,
    }
    tm.submit.assert_awaited_once_with(
        'batch_email',
        {'emails': ['test@example.com']},
        priority=1,
    )
