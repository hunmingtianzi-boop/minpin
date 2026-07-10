from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.api.errors import ApiError

router = APIRouter(tags=["Health"])


@router.get("/health/live", operation_id="getLiveness")
async def live() -> dict[str, object]:
    return {"data": {"status": "ok"}}


@router.get("/health/ready", operation_id="getReadiness")
async def ready(request: Request) -> dict[str, object]:
    database = getattr(request.app.state, "database", None)
    redis = getattr(request.app.state, "redis", None)
    if database is None or redis is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "服务正在启动，请稍后重试")
    try:
        async with database.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await redis.ping()
    except Exception as exc:
        # The exception is intentionally not returned to the client. Structured
        # request logging keeps the request id for internal correlation.
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "服务暂不可用，请稍后重试") from exc
    return {"data": {"status": "ready"}}
