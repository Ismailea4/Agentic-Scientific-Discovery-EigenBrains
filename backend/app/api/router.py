from fastapi import APIRouter

from .routes import health, stream, system

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(stream.router)
api_router.include_router(system.router)
