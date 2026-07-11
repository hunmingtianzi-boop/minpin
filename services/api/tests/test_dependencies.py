from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.api import dependencies
from app.core.config import Settings
from app.core.tokens import StaffPrincipal
from app.services.auth_store import StaffIdentity


async def test_staff_dependency_uses_current_membership_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_principal = StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role="company_admin",
        permissions=("*",),
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )
    current_identity = StaffIdentity(
        user_id=token_principal.user_id,
        membership_id=token_principal.membership_id,
        tenant_id=token_principal.tenant_id,
        company_id=token_principal.company_id,
        display_name="已降权员工",
        role="card_owner",
        permissions=("card.read",),
    )

    class CurrentIdentityStore:
        def __init__(self, _session_factory: Any, _settings: Settings) -> None:
            pass

        async def get_current(self, principal: StaffPrincipal) -> StaffIdentity:
            assert principal == token_principal
            return current_identity

    monkeypatch.setattr(
        dependencies,
        "decode_staff_access_token",
        lambda *_args, **_kwargs: token_principal,
    )
    monkeypatch.setattr(dependencies, "AuthStore", CurrentIdentityStore)
    settings = Settings(_env_file=None, app_env="test")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                session_factory=object(),
                require_staff_session_validation=True,
            )
        )
    )

    resolved = await dependencies.get_staff_principal(
        request,  # type: ignore[arg-type]
        authorization="Bearer signed-token",
    )

    assert resolved.role == "card_owner"
    assert resolved.permissions == ("card.read",)
    assert resolved.session_id == token_principal.session_id
    assert resolved.token_id == token_principal.token_id
