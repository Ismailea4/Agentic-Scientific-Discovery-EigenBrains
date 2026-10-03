from datetime import datetime, timezone

from fastapi import APIRouter

from ...config import settings

router = APIRouter(tags=["health"])


def health_status() -> dict[str, str]:
    return {
        "status": "ok",
        "version": settings.version,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return health_status()
