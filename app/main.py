"""FastAPI application for AI Workflow Automation."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import init_db
from app.routes.demo import router as demo_router
from app.routes.runs import router as runs_router
from app.routes.stream import router as stream_router
from app.routes.workflows import router as workflows_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("AI Workflow API starting up...")
    await init_db()
    yield
    logger.info("AI Workflow API shutting down...")
    from app.models import engine

    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AI Workflow Automation API",
        description="YAML-driven AI workflow automation with real-time streaming",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "Validation error", "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(stream_router, prefix="/api/v1")
    app.include_router(demo_router)

    return app


app = create_app()
