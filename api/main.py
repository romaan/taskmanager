from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.tasks import api as tasks_api
from configs import CONFIGS
from core.logging import setup_logging

# Initialize logging
setup_logging(level="INFO")

API_TITLE = "Task Management API"
API_VERSION = "0.1.0"


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """
    Application lifespan:
      - Create and wire core & app singletons
      - Start / stop background services
    """
    yield


def setup_routers(app: FastAPI) -> None:
    """
    Configure and include all application routers.
    """
    app.include_router(
        tasks_api.router,
    )


def setup_exceptions(app: FastAPI) -> None:
    pass


def setup_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Initialize FastAPI application with configuration
app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=app_lifespan)

setup_middleware(app)
setup_routers(app)
