from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.tasks import api as tasks_api
from apps.tasks.services.rate_limiter import RateLimiter
from apps.tasks.services.task_manager import TaskManager
from configs import CONFIGS
from core.exceptions import register_exception_handlers
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
    # --- Core wiring ---
    app.state.rate_limiter = RateLimiter(
        max_requests=CONFIGS['MAX_REQUESTS_PER_TIME_PER_IP'],
        period_seconds=CONFIGS['RATE_LIMIT_PERIOD'],
        cleanup_interval=CONFIGS.get('RATE_LIMIT_CLEANUP_INTERVAL', 300),
    )

    # --- Tasks runtime wiring ---
    app.state.task_manager = TaskManager(
        max_queue_size=CONFIGS['MAX_TASKS_QUEUE'],
        concurrency=CONFIGS['CONCURRENCY'],
        cleanup_after_seconds=CONFIGS['CLEANUP_INTERVAL'],
    )

    # --- Startup ---
    await app.state.rate_limiter.start_cleanup()
    await app.state.task_manager.start()

    try:
        yield  # Run while the server is alive
    finally:
        # --- Shutdown (reverse startup order) ---
        # Stop the task manager first if it may still enqueue requests
        await app.state.task_manager.stop()
        # Then stop the rate limiter's cleanup loop
        try:
            await app.state.rate_limiter.stop_cleanup()
        except Exception:
            # Be defensive during shutdown; don't block app teardown
            pass


def setup_routers(app: FastAPI) -> None:
    """
    Configure and include all application routers.

    Args:
        app: FastAPI application instance
    """
    app.include_router(
        tasks_api.router,
    )


def setup_exceptions(app: FastAPI) -> None:
    # map_validation_to_400=True makes validation errors 400 per your spec
    register_exception_handlers(app, map_validation_to_400=True)


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
setup_exceptions(app)
