import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from apps.tasks.depends.rate_limit import enforce_rate_limit
from apps.tasks.api import router as tasks_router
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
async def test_list_tasks(client):
    # Arrange
    tm = TaskManager()
    await tm.submit("batch_email",
                    {"emails": ["test@example.com", "abc@abc.com"]},
                    priority=1)
    await tm.submit("generate_report",
                    {"title": "Monthly Report", "sections": ["overview", "details", "summary"]},
                    priority=0)

    with patch("apps.tasks.api.get_task_manager", return_value=tm):
        # Act
        response = client.get("/api/v1/tasks")

    # Assert
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/jsonl")
    # Parse JSONL body
    lines = [ln for ln in response.text.strip().splitlines() if ln]
    assert len(lines) == 2

    objs = [json.loads(ln) for ln in lines]
    task_types = {o["task_type"] for o in objs}
    assert task_types == {"batch_email", "generate_report"}

    # Spot-check required fields are present
    for o in objs:
        assert "task_id" in o and isinstance(o["task_id"], str)  # UUID serialized as string
        assert "status" in o
        assert "parameters" in o


@pytest.mark.asyncio
async def test_list_tasks_with_filter(client):
    # Arrange
    tm = TaskManager()
    # create 3 tasks
    info1: TaskInfoModel = await tm.submit("batch_email",
                                           {"emails": ["test@example.com", "abc@abc.com"]},
                                           priority=1)  # initially "queued"
    info2: TaskInfoModel = await tm.submit("generate_report",
                                           {"title": "Monthly", "sections": ["overview"]},
                                           priority=0)  # initially "queued"
    info3: TaskInfoModel = await tm.submit("thumbnail_job",
                                           {"image_id": "img-123"},
                                           priority=2)  # initially "queued"

    # mutate statuses to have a mix
    tm.tasks[info1.task_id].info.status = "processing"
    tm.tasks[info2.task_id].info.status = "queued"
    tm.tasks[info3.task_id].info.status = "failed"

    with patch("apps.tasks.api.get_task_manager", return_value=tm):
        # Act: filter only queued
        resp = client.get("/api/v1/tasks", params={"status": "queued"})

    # Assert
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/jsonl")

    lines = [ln for ln in resp.text.strip().splitlines() if ln]
    # Only the generate_report task should match
    assert len(lines) == 1

    obj = json.loads(lines[0])
    assert obj["status"] == "queued"
    assert obj["task_type"] == "generate_report"
    assert obj["task_id"] == str(info2.task_id)
    assert "parameters" in obj


@pytest.mark.asyncio
async def test_list_tasks_with_filter_and_limit(client):
    # Arrange
    tm = TaskManager()
    # Create 5 tasks with mixed statuses
    for i in range(5):
        info = await tm.submit(
            "batch_email",
            {"emails": [f"user{i}@example.com"]},
            priority=i
        )
        # Assign alternating statuses
        tm.tasks[info.task_id].info.status = "completed" if i % 2 == 0 else "queued"

    with patch("apps.tasks.api.get_task_manager", return_value=tm):
        # Act: filter only completed tasks, limit to 2 results
        response = client.get("/api/v1/tasks", params={"status": "completed", "limit": 2})

    # Assert
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/jsonl")

    lines = [ln for ln in response.text.strip().splitlines() if ln]
    # Verify the limit worked — only 2 completed tasks returned
    assert len(lines) == 2

    objs = [json.loads(ln) for ln in lines]
    statuses = {o["status"] for o in objs}
    assert statuses == {"completed"}

    # Ensure correct structure
    for o in objs:
        assert o["task_type"] == "batch_email"
        assert "parameters" in o
        assert isinstance(o["task_id"], str)
