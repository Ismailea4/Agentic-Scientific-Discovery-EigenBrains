from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .api.routes.health import health_status
from .config import settings
from .core.errors import register_exception_handlers
from .core.logging import configure_logging
from .core.request_log import RequestLogMiddleware
from .system.registry import ArchitectureRegistry, CapabilityRegistry


def create_app() -> FastAPI:
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        file_enabled=settings.log_file_enabled,
        file_path=settings.log_file_path,
    )
    app = FastAPI(title=settings.app_name, version=settings.version)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last so it is the outermost middleware and sees the final status.
    app.add_middleware(RequestLogMiddleware)

    register_exception_handlers(app)
    app.state.capabilities = CapabilityRegistry()
    app.state.architectures = ArchitectureRegistry()
    app.include_router(api_router)

    # Also expose health at the app root so load balancers / devs can hit /health.
    app.add_api_route("/health", health_status, methods=["GET"], tags=["health"])

    return app


app = create_app()
