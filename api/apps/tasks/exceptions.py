class TaskFailedError(Exception):
    """Raised when a task fails due to simulated or real error."""
    pass


class QueueFullError(Exception):
    """Raised when the submission queue is full."""
    pass


class TaskNotCancellableError(Exception):
    """Raised when a cancel is requested but the task is already in a terminal state."""
    pass


class TaskCancellableError(Exception):
    """Raised when a task is cancelled"""
    pass