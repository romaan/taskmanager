import logging
import logging.config
from typing import TextIO


def setup_logging(level: str = "INFO") -> None:
    """
    Configure application logging.
    """
    fmt = "%(asctime)sZ | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {"format": fmt, "datefmt": datefmt}
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "plain",
            }
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn": {"level": level, "handlers": ["console"], "propagate": False},
            "uvicorn.error": {"level": level, "handlers": ["console"], "propagate": False},
            "uvicorn.access": {"level": level, "handlers": ["console"], "propagate": False},
        },
    })


class _StreamToLogger(TextIO):
    """File-like wrapper that redirects writes to a logger."""

    def __init__(self, logger: logging.Logger, level: int) -> None:
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, buf: str) -> int:  # type: ignore[override]
        self._buffer += buf
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self.logger.log(self.level, line)
        return len(buf)

    def flush(self) -> None:  # type: ignore[override]
        if self._buffer:
            self.logger.log(self.level, self._buffer.rstrip())
            self._buffer = ""
