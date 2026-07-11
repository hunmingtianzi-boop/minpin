from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import ApiError, api_error_handler
from app.api.routes import auth as auth_routes
from app.core.config import Settings
from app.core.tokens import issue_staff_tokens, issue_visitor_token
from app.services.auth_store import StaffAuthentication, StaffIdentity

AUTH_PREFIX = "/api/v1/auth"


class FakeAuthStore:
    def __init__(
        self,
        authentication: StaffAuthentication,
        refresh_authentication: StaffAuthentication,
    ) -> None:
        self.authentication = authentication
        self.refresh_authentication = refresh_authentication
        self.login_calls: list[tuple[str, str]] = []
        self.refresh_calls: list[str] = []
        self.logout_calls: list[Any] = []
        self.security_events: list[dict[str, Any]] = []

    async def login(
        self,
        *,
        account: str,
        credential: str,
        account_hash: str | None = None,
        request_ip_hash: str | None = None,
    ) -> StaffAuthentication:
        assert account_hash and len(account_hash) == 64
        assert request_ip_hash and len(request_ip_hash) == 64
        self.login_calls.append((account, credential))
        return self.authentication

    async def refresh(
        self,
        refresh_token: str,
        *,
        request_ip_hash: str | None = None,
    ) -> StaffAuthentication:
        assert request_ip_hash and len(request_ip_hash) == 64
        self.refresh_calls.append(refresh_token)
        return self.refresh_authentication

    async def logout(
        self,
        principal: Any,
        *,
        request_ip_hash: str | None = None,
    ) -> None:
        assert request_ip_hash and len(request_ip_hash) == 64
        self.logout_calls.append(principal)

    async def record_security_event(self, **values: Any) -> None:
        self.security_events.append(values)

    async def get_current(self, _principal: Any) -> StaffIdentity:
        return self.authentication.identity


def _test_app(monkeypatch: Any) -> tuple[TestClient, FakeAuthStore]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        app_name="auth-route-test",
        jwt_signing_key="r" * 32,
    )
    identity = StaffIdentity(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        display_name="路由管理员",
        role="company_admin",
        permissions=("card.publish",),
    )
    session_id = uuid.uuid4()
    tokens = issue_staff_tokens(
        signing_key=settings.jwt_signing_key.get_secret_value(),
        issuer=settings.app_name,
        access_ttl_seconds=600,
        refresh_ttl_seconds=3_600,
        user_id=identity.user_id,
        membership_id=identity.membership_id,
        tenant_id=identity.tenant_id,
        company_id=identity.company_id,
        role=identity.role,
        permissions=identity.permissions,
        session_id=session_id,
    )
    rotated_tokens = issue_staff_tokens(
        signing_key=settings.jwt_signing_key.get_secret_value(),
        issuer=settings.app_name,
        access_ttl_seconds=600,
        refresh_ttl_seconds=3_600,
        user_id=identity.user_id,
        membership_id=identity.membership_id,
        tenant_id=identity.tenant_id,
        company_id=identity.company_id,
        role=identity.role,
        permissions=identity.permissions,
        session_id=session_id,
    )
    store = FakeAuthStore(
        StaffAuthentication(tokens=tokens, identity=identity),
        StaffAuthentication(tokens=rotated_tokens, identity=identity),
    )
    monkeypatch.setattr(auth_routes, "_store", lambda _request: store)

    app = FastAPI()
    app.state.settings = settings
    app.state.session_factory = object()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(auth_routes.router, prefix=settings.api_prefix)
    return TestClient(app), store


def test_login_refresh_logout_and_me_contract(monkeypatch: Any) -> None:
    client, store = _test_app(monkeypatch)
    settings = client.app.state.settings

    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "admin@example.test",
            "credential": "correct-password",
            "method": "password",
        },
    )
    assert login.status_code == 200
    token_data = login.json()["data"]
    assert token_data["access_token"]
    assert token_data["csrf_token"]
    assert "refresh_token" not in token_data
    assert store.authentication.tokens.refresh_token not in login.text
    assert token_data["token_type"] == "Bearer"  # noqa: S105 - OAuth scheme
    assert token_data["expires_in"] <= 600
    assert store.login_calls == [("admin@example.test", "correct-password")]
    assert login.headers["x-csrf-token"] == token_data["csrf_token"]
    assert login.headers["cache-control"] == "no-store"
    login_cookie_headers = login.headers.get_list("set-cookie")
    refresh_cookie = next(
        item
        for item in login_cookie_headers
        if item.startswith(f"{settings.staff_refresh_cookie_name}=")
    )
    csrf_cookie = next(
        item
        for item in login_cookie_headers
        if item.startswith(f"{settings.staff_csrf_cookie_name}=")
    )
    assert "HttpOnly" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=strict" in refresh_cookie
    assert "Secure" not in refresh_cookie
    assert "Domain=" not in refresh_cookie
    assert f"Path={AUTH_PREFIX}" in refresh_cookie
    original_refresh = client.cookies.get(settings.staff_refresh_cookie_name)
    original_csrf = token_data["csrf_token"]
    assert original_refresh == store.authentication.tokens.refresh_token

    refresh = client.post(
        f"{AUTH_PREFIX}/refresh",
        headers={"X-CSRF-Token": original_csrf},
    )
    assert refresh.status_code == 200
    assert store.refresh_calls == [original_refresh]
    assert original_refresh not in refresh.text
    refreshed_data = refresh.json()["data"]
    assert "refresh_token" not in refreshed_data
    assert refreshed_data["csrf_token"] != original_csrf
    assert refresh.headers["x-csrf-token"] == refreshed_data["csrf_token"]
    assert refresh.headers["cache-control"] == "no-store"
    assert client.cookies.get(settings.staff_csrf_cookie_name) == refreshed_data["csrf_token"]
    assert client.cookies.get(settings.staff_refresh_cookie_name) == (
        store.refresh_authentication.tokens.refresh_token
    )
    assert client.cookies.get(settings.staff_refresh_cookie_name) != original_refresh
    stale_csrf = client.post(
        f"{AUTH_PREFIX}/refresh",
        headers={"X-CSRF-Token": original_csrf},
    )
    assert stale_csrf.status_code == 403
    assert store.refresh_calls == [original_refresh]

    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me = client.get(f"{AUTH_PREFIX}/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["user"]["display_name"] == "路由管理员"
    assert me.json()["data"]["membership"]["role"] == "company_admin"

    headers["X-CSRF-Token"] = refreshed_data["csrf_token"]
    logout = client.post(f"{AUTH_PREFIX}/logout", headers=headers)
    assert logout.status_code == 200
    assert logout.json() == {"data": {"revoked": True}}
    assert logout.headers["cache-control"] == "no-store"
    assert len(store.logout_calls) == 1
    assert client.cookies.get(settings.staff_refresh_cookie_name) is None
    assert client.cookies.get(settings.staff_csrf_cookie_name) is None
    logout_cookie_headers = logout.headers.get_list("set-cookie")
    assert sum("Max-Age=0" in item for item in logout_cookie_headers) == 2


def test_staff_dependency_rejects_visitor_token(monkeypatch: Any) -> None:
    client, store = _test_app(monkeypatch)
    settings = client.app.state.settings
    visitor_token, _ = issue_visitor_token(
        signing_key=settings.jwt_signing_key.get_secret_value(),
        issuer=settings.app_name,
        ttl_seconds=600,
        visitor_id=uuid.uuid4(),
        visit_id=uuid.uuid4(),
        tenant_id=store.authentication.identity.tenant_id,
        company_id=store.authentication.identity.company_id,
        card_id=uuid.uuid4(),
    )

    response = client.get(
        f"{AUTH_PREFIX}/me",
        headers={"Authorization": f"Bearer {visitor_token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_auth_router_operation_ids_are_stable(monkeypatch: Any) -> None:
    client, _ = _test_app(monkeypatch)
    paths = client.app.openapi()["paths"]

    assert paths[f"{AUTH_PREFIX}/login"]["post"]["operationId"] == "login"
    refresh_operation = paths[f"{AUTH_PREFIX}/refresh"]["post"]
    assert refresh_operation["operationId"] == "refreshStaffSession"
    assert "requestBody" not in refresh_operation
    assert any(
        parameter["name"] == "X-CSRF-Token" and parameter["in"] == "header"
        for parameter in refresh_operation["parameters"]
    )
    assert paths[f"{AUTH_PREFIX}/logout"]["post"]["operationId"] == "logoutStaffSession"
    assert paths[f"{AUTH_PREFIX}/me"]["get"]["operationId"] == "getCurrentUser"
    schemas = client.app.openapi()["components"]["schemas"]
    assert "RefreshRequest" not in schemas
    assert "refresh_token" not in schemas["StaffTokenData"]["properties"]


def test_refresh_requires_matching_double_submit_csrf(monkeypatch: Any) -> None:
    client, store = _test_app(monkeypatch)
    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "admin@example.test",
            "credential": "correct-password",
            "method": "password",
        },
    )
    csrf_token = login.json()["data"]["csrf_token"]

    missing = client.post(f"{AUTH_PREFIX}/refresh")
    mismatched = client.post(
        f"{AUTH_PREFIX}/refresh",
        headers={"X-CSRF-Token": f"{csrf_token}-forged"},
    )

    assert missing.status_code == 403
    assert mismatched.status_code == 403
    assert missing.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"
    assert store.refresh_calls == []
    csrf_events = [
        event
        for event in store.security_events
        if event.get("reason_code") == "csrf_validation_failed"
    ]
    assert len(csrf_events) == 2
    assert all(event["outcome"] == "blocked" for event in csrf_events)
    assert csrf_token not in repr(csrf_events)


def test_refresh_body_token_is_not_a_compatibility_fallback(monkeypatch: Any) -> None:
    client, store = _test_app(monkeypatch)
    settings = client.app.state.settings
    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "admin@example.test",
            "credential": "correct-password",
            "method": "password",
        },
    )
    csrf_token = login.json()["data"]["csrf_token"]
    raw_refresh = client.cookies.get(settings.staff_refresh_cookie_name)
    client.cookies.delete(settings.staff_refresh_cookie_name)

    response = client.post(
        f"{AUTH_PREFIX}/refresh",
        headers={"X-CSRF-Token": csrf_token},
        json={"refresh_token": raw_refresh},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
    assert store.refresh_calls == []
    assert store.security_events[-1]["reason_code"] == "refresh_cookie_missing"
    assert raw_refresh not in repr(store.security_events[-1])


def test_logout_requires_csrf_and_clears_both_cookies(monkeypatch: Any) -> None:
    client, store = _test_app(monkeypatch)
    settings = client.app.state.settings
    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "admin@example.test",
            "credential": "correct-password",
            "method": "password",
        },
    )
    token_data = login.json()["data"]
    authorization = {"Authorization": f"Bearer {token_data['access_token']}"}

    blocked = client.post(f"{AUTH_PREFIX}/logout", headers=authorization)

    assert blocked.status_code == 403
    assert store.logout_calls == []
    assert client.cookies.get(settings.staff_refresh_cookie_name)

    authorization["X-CSRF-Token"] = token_data["csrf_token"]
    logged_out = client.post(f"{AUTH_PREFIX}/logout", headers=authorization)

    assert logged_out.status_code == 200
    assert len(store.logout_calls) == 1
    assert client.cookies.get(settings.staff_refresh_cookie_name) is None
    assert client.cookies.get(settings.staff_csrf_cookie_name) is None


def test_secure_cookie_attribute_is_configurable_for_https(monkeypatch: Any) -> None:
    client, _ = _test_app(monkeypatch)
    client.app.state.settings.staff_auth_cookie_secure = True

    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "admin@example.test",
            "credential": "correct-password",
            "method": "password",
        },
    )

    cookie_headers = login.headers.get_list("set-cookie")
    assert len(cookie_headers) == 2
    assert all("Secure" in item for item in cookie_headers)


def test_login_ip_limit_is_shared_and_security_audited(monkeypatch: Any) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}
            self.keys: list[str] = []

        async def eval(
            self,
            _script: str,
            _number_of_keys: int,
            key: str,
            _window_seconds: int,
        ) -> tuple[int, int]:
            self.keys.append(key)
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key], 60

    client, store = _test_app(monkeypatch)
    client.app.state.settings.staff_login_ip_rate_limit_per_minute = 1
    redis = FakeRedis()
    client.app.state.redis = redis
    body = {
        "account": "admin@example.test",
        "credential": "correct-password",
        "method": "password",
    }

    first = client.post(f"{AUTH_PREFIX}/login", json=body)
    blocked = client.post(f"{AUTH_PREFIX}/login", json=body)

    assert first.status_code == 200
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.json()["error"]["message"] == "请求过于频繁，请稍后重试"
    assert len(store.login_calls) == 1
    assert store.security_events[-1]["event_type"] == "staff.login"
    assert store.security_events[-1]["outcome"] == "blocked"
    assert all("admin@example.test" not in key for key in redis.keys)


def test_login_account_limit_cannot_be_bypassed_by_case_or_whitespace(monkeypatch: Any) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}

        async def eval(
            self,
            _script: str,
            _number_of_keys: int,
            key: str,
            _window_seconds: int,
        ) -> tuple[int, int]:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key], 60

    client, store = _test_app(monkeypatch)
    client.app.state.settings.staff_login_ip_rate_limit_per_minute = 100
    client.app.state.settings.staff_login_account_rate_limit_per_minute = 1
    client.app.state.redis = FakeRedis()

    first = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "admin@example.test",
            "credential": "correct-password",
            "method": "password",
        },
    )
    blocked = client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "account": "  ADMIN@EXAMPLE.TEST  ",
            "credential": "correct-password",
            "method": "password",
        },
    )

    assert first.status_code == 200
    assert blocked.status_code == 429
    assert len(store.login_calls) == 1
    assert store.security_events[-1]["reason_code"] == "rate_limit_staff-login-account"
