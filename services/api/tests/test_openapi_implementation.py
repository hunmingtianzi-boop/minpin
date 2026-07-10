from __future__ import annotations

from app.main import app


def test_implemented_vertical_slice_uses_contract_operation_ids() -> None:
    paths = app.openapi()["paths"]
    expected = {
        ("/api/v1/health/live", "get"): "getLiveness",
        ("/api/v1/health/ready", "get"): "getReadiness",
        ("/api/v1/public/cards/{slug}", "get"): "getPublicCard",
        ("/api/v1/public/cards/{slug}/visits", "post"): "createVisit",
        ("/api/v1/public/cards/{slug}/consents", "post"): "recordConsent",
        ("/api/v1/public/cards/{slug}/conversations", "post"): "createConversation",
        (
            "/api/v1/public/conversations/{conversation_id}/messages:stream",
            "post",
        ): "streamConversationMessage",
    }

    for (path, method), operation_id in expected.items():
        assert paths[path][method]["operationId"] == operation_id

