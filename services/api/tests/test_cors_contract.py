from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_admin_origin_can_send_if_match_and_read_etag() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            cors_allowed_origins=["http://admin.example.test"],
        )
    )
    client = TestClient(app)

    response = client.options(
        "/api/v1/admin/company/profile",
        headers={
            "Origin": "http://admin.example.test",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": (
                "authorization,content-type,if-match,x-csrf-token"
            ),
        },
    )

    assert response.status_code == 200
    assert "if-match" in response.headers["access-control-allow-headers"].lower()
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-credentials"] == "true"

    actual_response = client.get(
        "/api/v1/health/live",
        headers={"Origin": "http://admin.example.test"},
    )
    assert actual_response.status_code == 200
    assert "etag" in actual_response.headers["access-control-expose-headers"].lower()
    assert "x-csrf-token" in actual_response.headers["access-control-expose-headers"].lower()
    assert actual_response.headers["access-control-allow-credentials"] == "true"
