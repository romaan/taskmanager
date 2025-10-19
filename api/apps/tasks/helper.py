from fastapi import Request

from apps.tasks.services.task_manager import TaskManager


def get_task_manager(request: Request) -> TaskManager:
    """
    Helper to get the task manager from the request.
    :param request:
    :return:
    """
    tm: TaskManager = request.app.state.task_manager  # type: ignore[attr-defined]
    return tm