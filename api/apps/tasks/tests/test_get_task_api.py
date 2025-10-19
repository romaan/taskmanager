import asyncio
from asyncio import CancelledError
from datetime import datetime, timedelta, timezone
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.tasks.api import router as tasks_router
from apps.tasks.depends.rate_limit import enforce_rate_limit
from apps.tasks.models.task_manager import TaskInfoModel, TaskRecordModel
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
async def test_get_task_api(client):
    """Return current info immediately (200)."""
    tm = TaskManager()
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    tid = uuid4()

    tfm = TaskInfoModel(task_id=tid, status="queued", task_type="batch_email",
                        parameters={"emails": [f"test1@test.com"]})
    tm.tasks[tfm.task_id] = TaskRecordModel(info=tfm, created_at=now, updated_at=now)

    with patch("apps.tasks.api.get_task_manager", return_value=tm):
        start = perf_counter()
        resp = client.get(f"/api/v1/tasks/{str(tid)}")
        elapsed = perf_counter() - start
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task_id"] == str(tid)
    assert body["status"] == "queued"
    assert body["task_type"] == "batch_email"
    assert body["parameters"] == {"emails": [f"test1@test.com"]}
    assert elapsed < 1, f"elapsed={elapsed:.3f}s should be < 1s"


@pytest.mark.asyncio
async def test_get_task_api_with_wait(client):
    """
    If wait is provided and the task finishes within that period, the final status is returned.
    """
    tm = TaskManager()
    tid = uuid4()
    timeout = 5

    # Submit a task with mocked UUID
    with patch("apps.tasks.services.task_manager.TaskManager._generate_uuid", return_value=tid):
        await tm.submit("generate_report",
                        {"title": "Monthly Report", "sections": ["overview", "details", "summary"]},
                        priority=0)

    await tm.start()

    with patch("apps.tasks.api.get_task_manager", return_value=tm):
        start = perf_counter()
        resp = client.get(f"/api/v1/tasks/{str(tid)}?wait=true&timeout={timeout}")
        elapsed = perf_counter() - start

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["task_id"] == str(tid)
    # Allow a small scheduling tolerance (<0.25s) to avoid flakiness in CI.
    assert elapsed >= timeout - 0.25, f"elapsed={elapsed:.3f}s < expected ~{timeout}s"
    # Since the tasks are running while stop, CancelledError is raised
    with pytest.raises(CancelledError):
        await tm.stop()

@pytest.mark.asyncio
async def test_get_task_api_not_found(client):
    """Unknown task_id -> 404 with your standardized error envelope."""
    tm = TaskManager()
    tid = uuid4()

    with patch("apps.tasks.api.get_task_manager", return_value=tm):
        resp = client.get(f"/api/v1/tasks/{str(tid)}")

    assert resp.status_code == 404, resp.text
    # Your setup_exceptions wraps HTTPException into:
    err = resp.json()
    assert err == {
        "code": "not_found",
        "details": None,
        "message": "Task not found",
        "request_id": None,
    }, f"Unexpected error response: {err}"
