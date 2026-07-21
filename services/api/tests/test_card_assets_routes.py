from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import card_assets
from app.core.tokens import StaffPrincipal
from app.services.card_assets import (
    CardAssetContent,
    CardAssetNotFoundError,
    ProcessedCardAsset,
    StoredCardAsset,
)


class FakeCardAssetStore:
    def __init__(self) -> None:
        self.asset_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        self.put_calls: list[dict[str, Any]] = []
        self.missing = False

    async def put(
        self,
        *,
        company_id: uuid.UUID,
        asset: ProcessedCardAsset,
    ) -> StoredCardAsset:
        self.put_calls.append({"company_id": company_id, "asset": asset})
        return StoredCardAsset(
            asset_id=self.asset_id,
            width=asset.width,
            height=asset.height,
            size_bytes=len(asset.payload),
            content_type=asset.content_type,
        )

    async def get(self, *, company_id: uuid.UUID, asset_id: uuid.UUID) -> CardAssetContent:
        if self.missing:
            raise CardAssetNotFoundError
        assert asset_id == self.asset_id
        return CardAssetContent(payload=b"webp-image", content_type="image/webp")


@pytest.fixture
def asset_client() -> tuple[TestClient, FakeCardAssetStore, dict[str, StaffPrincipal]]:
    store = FakeCardAssetStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.state.settings = SimpleNamespace(api_prefix="/api/v1")
    app.state.card_asset_store = store
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(card_assets.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    with TestClient(app) as client:
        yield client, store, principal_box


def _principal(
    *,
    role: str,
    permissions: tuple[str, ...] = (),
) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role=role,
        permissions=permissions,
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (48, 32), (50, 100, 220, 180)).save(output, format="PNG")
    return output.getvalue()


def test_card_asset_upload_is_company_scoped_and_normalized_to_webp(
    asset_client: tuple[TestClient, FakeCardAssetStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = asset_client

    response = client.post(
        "/api/v1/admin/card-assets",
        files={"file": ("avatar.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 201
    assert store.put_calls[0]["company_id"] == principal_box["value"].company_id
    processed = store.put_calls[0]["asset"]
    assert processed.payload.startswith(b"RIFF")
    assert processed.content_type == "image/webp"
    assert response.json()["data"] == {
        "url": (
            f"/api/v1/public/card-assets/{principal_box['value'].company_id}/"
            f"{store.asset_id}.webp"
        ),
        "content_type": "image/webp",
        "width": 48,
        "height": 32,
        "size_bytes": len(processed.payload),
    }


def test_card_asset_upload_rejects_fake_or_unauthorized_images(
    asset_client: tuple[TestClient, FakeCardAssetStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = asset_client

    invalid = client.post(
        "/api/v1/admin/card-assets",
        files={"file": ("avatar.png", b"not-an-image", "image/png")},
    )
    principal_box["value"] = _principal(role="card_owner")
    forbidden = client.post(
        "/api/v1/admin/card-assets",
        files={"file": ("avatar.png", _png_bytes(), "image/png")},
    )

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "CARD_ASSET_INVALID_IMAGE"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    assert store.put_calls == []


def test_public_card_asset_returns_immutable_image_or_404(
    asset_client: tuple[TestClient, FakeCardAssetStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = asset_client
    url = (
        f"/api/v1/public/card-assets/{principal_box['value'].company_id}/"
        f"{store.asset_id}.webp"
    )

    response = client.get(url)
    store.missing = True
    missing = client.get(url)

    assert response.status_code == 200
    assert response.content == b"webp-image"
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CARD_ASSET_NOT_FOUND"
