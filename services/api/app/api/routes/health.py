from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import Response
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


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    settings = request.app.state.settings
    configured = settings.metrics_bearer_token
    if configured is not None:
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {configured.get_secret_value()}"
        if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            raise ApiError(
                401,
                "METRICS_UNAUTHORIZED",
                "监控凭证无效",
                headers={"WWW-Authenticate": "Bearer"},
            )

    registry = request.app.state.metrics
    database = getattr(request.app.state, "database", None)
    pool = getattr(getattr(database, "sync_engine", None), "pool", None)
    if pool is not None:
        pool_values = {
            "size": getattr(pool, "size", lambda: 0)(),
            "checked_out": getattr(pool, "checkedout", lambda: 0)(),
            "overflow": getattr(pool, "overflow", lambda: 0)(),
        }
        for state, value in pool_values.items():
            registry.gauge(
                "cf_db_pool_connections",
                float(value),
                labels={"state": state},
                help_text="SQLAlchemy connection pool state.",
            )
    return Response(
        registry.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
