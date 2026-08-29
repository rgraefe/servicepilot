from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any
from uuid import uuid4
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError
from pydantic import BaseModel

from app.api import appointments, customers, handover, tickets
from app.config import get_settings
from app.container import build_container
from app.errors import ServiceError
from app.observability import (
    REQUEST_ID,
    TRACE_RESOURCE,
    cloud_trace_resource,
    configure_logging,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    persistence_backend: str


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    application.state.container = build_container(settings)
    application.state.logger.info(
        "application_started",
        extra={
            "event": "application_started",
            "environment": settings.environment,
            "persistence_backend": settings.persistence_backend,
        },
    )
    try:
        yield
    finally:
        application.state.logger.info(
            "application_stopped", extra={"event": "application_stopped"}
        )


def error_body(code: str, message: str, retryable: bool, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if details is not None:
        error["details"] = details
    return {"error": error}


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="ServicePilot API",
        version="0.3.0",
        description="Deterministic customer-service backend",
        lifespan=lifespan,
    )
    application.state.logger = configure_logging(settings.log_level)

    @application.middleware("http")
    async def structured_request_logging(request: Request, call_next):
        supplied_request_id = request.headers.get("x-request-id")
        request_id = (
            supplied_request_id
            if supplied_request_id
            and _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else uuid4().hex
        )
        request_id_token = REQUEST_ID.set(request_id)
        trace_token = TRACE_RESOURCE.set(
            cloud_trace_resource(
                request.headers.get("x-cloud-trace-context"),
                settings.firestore_project,
            )
        )
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        except Exception as exc:
            application.state.logger.error(
                "request_failed",
                extra={"event": "request_failed", "error_type": type(exc).__name__},
            )
            raise
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", "<unmatched>")
            elapsed = perf_counter() - started
            application.state.logger.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "route": route_template,
                    "httpRequest": {
                        "requestMethod": request.method,
                        "status": status_code,
                        "latency": f"{elapsed:.6f}s",
                        "protocol": f"HTTP/{request.scope.get('http_version', '1.1')}",
                    },
                },
            )
            TRACE_RESOURCE.reset(trace_token)
            REQUEST_ID.reset(request_id_token)

    @application.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.retryable),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": [str(part) for part in error["loc"]],
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "The request did not satisfy the API schema.",
                False,
                details,
            ),
        )

    @application.exception_handler(GoogleAPICallError)
    async def persistence_error_handler(
        _: Request, __: GoogleAPICallError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_body(
                "PERSISTENCE_UNAVAILABLE",
                "The persistence service is temporarily unavailable.",
                True,
            ),
        )

    @application.get("/health", response_model=HealthResponse, tags=["operations"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="servicepilot-api",
            environment=settings.environment,
            persistence_backend=application.state.container.persistence_backend,
        )

    application.include_router(customers.router)
    application.include_router(tickets.router)
    application.include_router(appointments.router)
    application.include_router(handover.router)
    return application


app = create_app()
