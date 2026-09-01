from __future__ import annotations

import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.api.auth import (
    AuthenticationMiddleware,
    AuthSettings,
    AuthUser,
    SessionAuthenticator,
    authenticated_client_id,
    create_auth_router,
    hash_password,
    verify_password,
)

PASSWORD = "correct-horse-battery-staple"
PASSWORD_HASH = hash_password(PASSWORD, salt=b"fixed-test-auth-salt")


def _settings(*, enabled: bool = True, ttl: int = 3600) -> AuthSettings:
    return AuthSettings(
        enabled=enabled,
        users=(
            AuthUser("viewer", PASSWORD_HASH, "viewer", "tenant-a"),
            AuthUser("operator", PASSWORD_HASH, "operator", "tenant-a"),
            AuthUser("admin", PASSWORD_HASH, "admin", "tenant-a"),
        ),
        session_secret="test-session-secret-that-is-longer-than-32-characters",
        session_ttl_seconds=ttl,
        cookie_secure=True,
    )


def _client(*, enabled: bool = True) -> TestClient:
    authenticator = SessionAuthenticator(_settings(enabled=enabled))
    app = FastAPI()

    @app.get("/api/v1/protected")
    def read(request: Request) -> dict[str, str]:
        return {
            "client_id": authenticated_client_id(request, "untrusted-client"),
            "tenant": getattr(request.state, "tenant_id", ""),
        }

    @app.post("/api/v1/protected")
    def mutate() -> dict[str, bool]:
        return {"ok": True}

    @app.delete("/api/v1/protected")
    def remove() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(create_auth_router(authenticator), prefix="/api/v1")
    app.add_middleware(AuthenticationMiddleware, authenticator=authenticator)
    return TestClient(app, base_url="https://testserver")


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200


def test_passwords_are_one_way_hashed_and_verified() -> None:
    assert PASSWORD not in PASSWORD_HASH
    assert verify_password(PASSWORD, PASSWORD_HASH)
    assert not verify_password("incorrect-password", PASSWORD_HASH)


def test_protected_api_rejects_anonymous_and_invalid_login() -> None:
    client = _client()

    anonymous = client.get("/api/v1/protected")
    invalid = client.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": "incorrect"},
    )

    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401


def test_login_sets_secure_http_only_cookie_and_principal_identity() -> None:
    client = _client()
    _login(client, "viewer")

    cookie = client.cookies.get("bist_session")
    response = client.get("/api/v1/protected")

    assert cookie
    assert "HttpOnly" in client.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": PASSWORD},
    ).headers["set-cookie"]
    assert "Secure" in client.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": PASSWORD},
    ).headers["set-cookie"]
    assert response.status_code == 200
    assert response.json()["client_id"].startswith("auth-")
    assert response.json()["tenant"] == "tenant-a"


def test_role_policy_separates_read_mutation_and_delete() -> None:
    viewer = _client()
    operator = _client()
    admin = _client()
    _login(viewer, "viewer")
    _login(operator, "operator")
    _login(admin, "admin")

    assert viewer.get("/api/v1/protected").status_code == 200
    assert viewer.post("/api/v1/protected").status_code == 403
    assert operator.post("/api/v1/protected").status_code == 200
    assert operator.delete("/api/v1/protected").status_code == 403
    assert admin.delete("/api/v1/protected").status_code == 200


def test_tenant_header_cannot_cross_authenticated_boundary() -> None:
    client = _client()
    _login(client, "admin")

    response = client.get(
        "/api/v1/protected",
        headers={"X-Tenant-ID": "tenant-b"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TENANT_BOUNDARY_VIOLATION"


def test_tampered_and_expired_tokens_are_rejected() -> None:
    settings = _settings()
    authenticator = SessionAuthenticator(settings)
    principal = authenticator.authenticate("admin", PASSWORD)
    assert principal is not None
    issued_at = time.time()
    token = authenticator.issue(principal)

    assert authenticator.resolve_token(f"{token}tampered") is None
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(time, "time", lambda: issued_at + 7200)
        assert authenticator.resolve_token(token) is None


def test_authentication_can_be_disabled_for_single_process_development() -> None:
    response = _client(enabled=False).post("/api/v1/protected")

    assert response.status_code == 200
