import asyncio
import logging
from uuid import uuid4
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Path, Request, Response, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from apps.tasks.models.task_manager import (TaskInfoModel, TaskModel, TaskSummaryModel, TaskRecordModel)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["Tasks"]
)


# ---------------------------------
# POST /api/v1/tasks  (create_task)
# ---------------------------------
@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskSummaryModel,
)
async def create_task(payload: TaskModel, request: Request) -> TaskSummaryModel:
    """
    Submit a task. \r\n
    Validation is handled by Pydantic before this runs.
    Returns 202 Accepted with TaskSummaryModel \r\n
    Returns 400 Bad Request if validation fails. \r\n
    Returns 503 QueueFull if task queue is full. Try again later. \r\n
    """
    task_type = payload.task_type
    priority = getattr(payload, "priority", 0)

    raise HTTPException(status_code=503, detail="Task queue is full. Try again later.")


# ----------------------------------------
# GET /api/v1/tasks/{task_id}  (get_task)
# ----------------------------------------
@router.get(
    "/{task_id}",
    response_model=TaskInfoModel,
)
async def get_task(
    task_id: str,
    request: Request,
    wait: bool = Query(False, description="Enable long-poll, wait for a status change"),
    timeout: int = Query(10, ge=1, le=60, description="Long-poll timeout in seconds"),
) -> TaskInfoModel:
    """
    Retrieve information about a task by its ID. \r\n

    This endpoint fetches the status and details of a task using its unique identifier.
    Optionally, it supports long-polling to wait for a status change before returning
    the response. If the task ID does not exist, an HTTP 404 error is raised.
    """
    return TaskInfoModel(task_id=uuid4(), status="cancelled", task_type="batch_email", parameters={})


# -------------------------------
# GET /api/v1/tasks  (list_tasks)
# -------------------------------
@router.get(
    "",
    response_class=StreamingResponse,
    summary="List tasks (optionally filter by status). Streams JSONL.",
)
async def list_tasks(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status", description='Filter by status: "queued", "processing", "completed", "failed", "cancelled"'),
    limit: int = Query(10, ge=1, le=1000),
) -> StreamingResponse:
    """
    Lists tasks, optionally filtering by their status. Streams the result in JSON Lines format (`JSONL`).\r\n

    This function provides a listing of tasks managed by the task manager system. It supports optional
    filtering of tasks based on their status and limits the number of tasks returned in the stream.
    Tasks are serialized to JSONL format for efficient streaming and transferred to the client incrementally
    to optimize memory usage.
    """

    async def _stream() -> AsyncGenerator[bytes, None]:
        count = 0
        # Snapshot current tasks to avoid holding locks while streaming
        for rec in list(["value1", "value2"]):  # type: ignore[attr-defined]
            if status_filter and rec.info.status != status_filter:
                continue
            # Prefer model's .json(); fallback to json.dumps on .dict()
            try:
                line = rec.info.model_dump_json()
                yield (line + "\n").encode("utf-8")
            except AttributeError as e:
                logger.error(e)
            count += 1
            if count >= limit:
                break
            # be cooperative to event loop
            await asyncio.sleep(0)

    return StreamingResponse(_stream(), media_type="application/jsonl")


@router.delete(
    "/{task_id}",
    response_model=TaskInfoModel,  # keep response_model
    responses={
        200: {"description": "Task cancelled / not running"},
        202: {"description": "Cancellation requested (task already running)"},
        404: {"description": "Task not found"},
    },
)
async def cancel_task(
    request: Request,
    response: Response,
    task_id: str = Path(..., description="Task ID (UUID)"),
    wait: bool = Query(False, description="Wait for the task to reach a new state"),
    timeout: int = Query(10, ge=1, le=60, description="Wait timeout in seconds"),
) -> TaskInfoModel:
    """
    handles the cancellation of a task with a specified task ID. \r\n

    - 404 if the task doesn't exist **or** is already in a terminal state (completed/failed/cancelled).
    - 202 if the task is processing (cancellation requested).
    - 200 if the task was queued and is now cancelled immediately.
    """

    raise HTTPException(status_code=404, detail=str("Task not found"))
