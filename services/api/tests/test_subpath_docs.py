from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_docs_use_the_production_api_subpath() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            asgi_root_path="/c",
            api_docs_enabled=True,
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/docs")

    assert response.status_code == 200
    assert "/c/api/openapi.json" in response.text
