import asyncio
from datetime import datetime, timezone

from apps.tasks.models.task import PARAM_MODELS, TASK_TYPES
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    model_validator,
    PrivateAttr
)
from typing import Any, Dict, Literal, Optional, TypedDict

from uuid import UUID

TaskStatusModel = Literal["queued",
                          "processing",
                          "completed",
                          "failed",
                          "cancelled"]


class TaskModel(BaseModel):
    task_type: TASK_TYPES = Field(description="Type of task")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(0, ge=0, le=10, description="Optional priority (0-10). Lower means earlier.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "parameters": {
                        "numbers": [1, 2, 3]
                    },
                    "priority": 10,
                    "task_type": "compute_sum"
                },
                {
                    "task_type": "generate_report",
                    "parameters": {
                        "title": "Monthly Report"
                    },
                    "priority": 1
                }
            ]
        }
    }

    @model_validator(mode="before")
    @classmethod
    def validate_parameters_by_task_type(cls, data: Dict[str, Any]):
        t = data.get("task_type")
        p = data.get("parameters") or {}
        model = PARAM_MODELS.get(t)
        if not model:
            # Let FastAPI/Pydantic handle the task_type validation
            return data
        try:
            parsed = model.model_validate(p)
        except ValidationError as ve:
            raise ve
        data["parameters"] = parsed.model_dump()
        return data


class ProgressInfoModel(BaseModel):
    message: str
    started_at: Optional[datetime] = None
    eta_seconds: Optional[int] = None


class TaskInfoModel(BaseModel):
    task_id: UUID
    status: TaskStatusModel
    task_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: Optional[int] = Field(default=0, ge=0, le=100)
    progress_info: Optional[ProgressInfoModel] = None


class TaskRecordModel(BaseModel):
    info: TaskInfoModel
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cancel_requested: bool = False
    started_monotonic: Optional[float] = None
    est_total_seconds: Optional[int] = None

    _event: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def event(self) -> asyncio.Event:
        return self._event


class TaskListModel(BaseModel):
    tasks: list[TaskInfoModel]


class TaskSummaryModel(TypedDict):
    task_id: UUID
    status: TaskStatusModel

