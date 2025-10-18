from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Type, Literal


class ComputeSumParams(BaseModel):

    numbers: list[float] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")


class GenerateReportParams(BaseModel):

    title: str = Field(..., min_length=1)
    sections: list[str] = Field(default_factory=lambda: ["overview", "details", "summary"])

    model_config = ConfigDict(extra="forbid")


class BatchEmailParams(BaseModel):

    emails: list[EmailStr] = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")


class LuckyJobParams(BaseModel):

    model_config = ConfigDict(extra="forbid")


TASK_TYPES = Literal["compute_sum", "generate_report", "batch_email", "lucky_job"]

PARAM_MODELS: dict[str, Type[BaseModel]] = {
    "compute_sum": ComputeSumParams,
    "generate_report": GenerateReportParams,
    "batch_email": BatchEmailParams,
    "lucky_job": LuckyJobParams,
}
