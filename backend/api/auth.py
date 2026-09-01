"""Authentication, coarse RBAC, and single-tenant request boundaries."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, NoReturn

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.api.error_mapping import error_envelope

Role = Literal["viewer", "operator", "admin"]

_ROLE_LEVEL: dict[str, int] = {"viewer": 10, "operator": 20, "admin": 30}
_PUBLIC_PATHS = frozenset(
    {
        "/healthz",
        "/livez",
        "/readyz",
        "/api/v1/auth/login",
        "/api/v1/auth/session",
        "/api/auth/login",
        "/api/auth/session",
    }
)


def _environment_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


@dataclass(frozen=True, slots=True)
class AuthUser:
    username: str
    password_hash: str
    role: Role
    tenant_id: str

    @property
    def client_id(self) -> str:
        digest = hashlib.sha256(
            f"{self.tenant_id}:{self.username}".encode("utf-8")
        ).hexdigest()[:32]
        return f"auth-{digest}"


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    username: str
    role: Role
    tenant_id: str
    client_id: str


@dataclass(frozen=True, slots=True)
class AuthSettings:
    enabled: bool = False
    users: tuple[AuthUser, ...] = ()
    session_secret: str = ""
    session_ttl_seconds: int = 28_800
    cookie_name: str = "bist_session"
    cookie_secure: bool = False

    @classmethod
    def from_environment(cls) -> AuthSettings:
        app_env = os.getenv("APP_ENV", "development").strip().casefold()
        enabled = _environment_bool("AUTH_ENABLED", False)
        cookie_secure = _environment_bool(
            "AUTH_COOKIE_SECURE",
            app_env in {"production", "prod"},
        )
        ttl = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "28800"))
        raw_users = os.getenv("AUTH_USERS_JSON", "").strip()
        users: list[AuthUser] = []
        if raw_users:
            parsed = json.loads(raw_users)
            if not isinstance(parsed, list):
                raise ValueError("AUTH_USERS_JSON must be a JSON array")
            for entry in parsed:
                if not isinstance(entry, dict):
                    raise ValueError("AUTH_USERS_JSON entries must be objects")
                role = str(entry.get("role", "")).strip().casefold()
                if role not in _ROLE_LEVEL:
                    raise ValueError("AUTH_USERS_JSON role must be viewer/operator/admin")
                users.append(
                    AuthUser(
                        username=str(entry.get("username", "")).strip(),
                        password_hash=str(entry.get("password_hash", "")),
                        role=role,  # type: ignore[arg-type]
                        tenant_id=str(entry.get("tenant_id", "")).strip(),
                    )
                )

        settings = cls(
            enabled=enabled,
            users=tuple(users),
            session_secret=os.getenv("AUTH_SESSION_SECRET", ""),
            session_ttl_seconds=ttl,
            cookie_name=os.getenv("AUTH_COOKIE_NAME", "bist_session").strip(),
            cookie_secure=cookie_secure,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.enabled:
            return
        if len(self.session_secret) < 32:
            raise ValueError("AUTH_SESSION_SECRET must contain at least 32 characters")
        if self.session_ttl_seconds < 300 or self.session_ttl_seconds > 86_400:
            raise ValueError("AUTH_SESSION_TTL_SECONDS must be between 300 and 86400")
        if not self.cookie_name:
            raise ValueError("AUTH_COOKIE_NAME must not be blank")
        if not self.users:
            raise ValueError("AUTH_USERS_JSON must define at least one user")
        usernames: set[str] = set()
        for user in self.users:
            if (
                len(user.username) < 3
                or not _is_supported_password_hash(user.password_hash)
                or not user.tenant_id
            ):
                raise ValueError(
                    "auth users require username>=3, a PBKDF2 password_hash, and tenant_id"
                )
            if user.username in usernames:
                raise ValueError("AUTH_USERS_JSON usernames must be unique")
            usernames.add(user.username)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class PrincipalResponse(BaseModel):
    username: str
    role: Role
    tenant_id: str
    client_id: str


class SessionResponse(BaseModel):
    enabled: bool
    authenticated: bool
    principal: PrincipalResponse | None = None


class SessionAuthenticator:
    """Verify configured credentials and issue short-lived signed cookies."""

    def __init__(self, settings: AuthSettings) -> None:
        settings.validate()
        self.settings = settings
        self._users = {user.username: user for user in settings.users}

    def authenticate(self, username: str, password: str) -> AuthPrincipal | None:
        user = self._users.get(username)
        candidate_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_matches = verify_password(password, candidate_hash)
        if user is None or not password_matches:
            return None
        return self._principal(user)

    def issue(self, principal: AuthPrincipal) -> str:
        payload = {
            "iss": "excel-rag",
            "sub": principal.username,
            "tenant": principal.tenant_id,
            "exp": int(time.time()) + self.settings.session_ttl_seconds,
        }
        encoded = _b64url_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signature = hmac.new(
            self.settings.session_secret.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded}.{_b64url_encode(signature)}"

    def resolve(self, request: Request) -> AuthPrincipal | None:
        token = request.cookies.get(self.settings.cookie_name)
        authorization = request.headers.get("Authorization", "")
        if not token and authorization.casefold().startswith("bearer "):
            token = authorization[7:].strip()
        return self.resolve_token(token)

    def resolve_token(self, token: str | None) -> AuthPrincipal | None:
        if not token or "." not in token:
            return None
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(
            self.settings.session_secret.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        try:
            actual = _b64url_decode(signature)
            payload = json.loads(_b64url_decode(encoded))
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
        if not hmac.compare_digest(expected, actual) or not isinstance(payload, dict):
            return None
        try:
            expires_at = int(payload.get("exp", 0))
        except (TypeError, ValueError):
            return None
        if payload.get("iss") != "excel-rag" or expires_at <= int(time.time()):
            return None
        username = str(payload.get("sub", ""))
        tenant = str(payload.get("tenant", ""))
        user = self._users.get(username)
        if user is None or not hmac.compare_digest(user.tenant_id, tenant):
            return None
        return self._principal(user)

    @staticmethod
    def _principal(user: AuthUser) -> AuthPrincipal:
        return AuthPrincipal(
            username=user.username,
            role=user.role,
            tenant_id=user.tenant_id,
            client_id=user.client_id,
        )


def _required_role(request: Request) -> Role:
    if request.url.path.endswith("/auth/logout"):
        return "viewer"
    if request.method == "DELETE":
        return "admin"
    if request.method in {"POST", "PUT", "PATCH"}:
        return "operator"
    return "viewer"


def _auth_error(status_code: int, code: str, message: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=status_code,
        content=error_envelope(code=code, message=message),
        headers=headers,
    )


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Protect API routes and attach immutable principal/tenant context."""

    def __init__(self, app: Any, authenticator: SessionAuthenticator) -> None:
        super().__init__(app)
        self.authenticator = authenticator

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        settings = self.authenticator.settings
        if not settings.enabled or request.method == "OPTIONS":
            request.state.auth_principal = None
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_PATHS or not (path == "/api" or path.startswith("/api/")):
            request.state.auth_principal = self.authenticator.resolve(request)
            return await call_next(request)

        principal = self.authenticator.resolve(request)
        if principal is None:
            return _auth_error(401, "AUTHENTICATION_REQUIRED", "로그인이 필요합니다.")

        requested_tenant = request.headers.get("X-Tenant-ID", "").strip()
        if requested_tenant and not hmac.compare_digest(
            requested_tenant,
            principal.tenant_id,
        ):
            return _auth_error(
                403,
                "TENANT_BOUNDARY_VIOLATION",
                "현재 계정의 tenant 범위를 벗어난 요청입니다.",
            )

        required = _required_role(request)
        if _ROLE_LEVEL[principal.role] < _ROLE_LEVEL[required]:
            return _auth_error(
                403,
                "ROLE_PERMISSION_DENIED",
                f"이 작업에는 {required} 권한이 필요합니다.",
            )

        request.state.auth_principal = principal
        request.state.tenant_id = principal.tenant_id
        request.state.audit_actor_id = principal.username
        return await call_next(request)


def create_auth_router(authenticator: SessionAuthenticator) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["Authentication"])

    @router.post("/login", response_model=SessionResponse)
    def login(payload: LoginRequest, response: Response) -> SessionResponse:
        settings = authenticator.settings
        if not settings.enabled:
            return SessionResponse(enabled=False, authenticated=False)
        principal = authenticator.authenticate(payload.username, payload.password)
        if principal is None:
            raise_authentication_error()
        response.set_cookie(
            key=settings.cookie_name,
            value=authenticator.issue(principal),
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return _session_response(principal, enabled=True)

    @router.get("/session", response_model=SessionResponse)
    def session(request: Request) -> SessionResponse:
        settings = authenticator.settings
        if not settings.enabled:
            return SessionResponse(enabled=False, authenticated=False)
        principal = authenticator.resolve(request)
        if principal is None:
            raise_authentication_error()
        return _session_response(principal, enabled=True)

    @router.post("/logout", response_model=SessionResponse)
    def logout(response: Response) -> SessionResponse:
        settings = authenticator.settings
        response.delete_cookie(
            settings.cookie_name,
            path="/",
            secure=settings.cookie_secure,
            httponly=True,
            samesite="strict",
        )
        response.headers["Cache-Control"] = "no-store"
        return SessionResponse(enabled=settings.enabled, authenticated=False)

    return router


def raise_authentication_error() -> NoReturn:
    from fastapi import HTTPException

    raise HTTPException(
        status_code=401,
        detail={
            "code": "INVALID_CREDENTIALS",
            "message": "아이디 또는 비밀번호가 올바르지 않습니다.",
            "retryable": False,
            "context": {},
        },
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


def _session_response(principal: AuthPrincipal, *, enabled: bool) -> SessionResponse:
    return SessionResponse(
        enabled=enabled,
        authenticated=True,
        principal=PrincipalResponse(
            username=principal.username,
            role=principal.role,
            tenant_id=principal.tenant_id,
            client_id=principal.client_id,
        ),
    )


def authenticated_client_id(request: Request, fallback: str) -> str:
    principal = getattr(request.state, "auth_principal", None)
    if isinstance(principal, AuthPrincipal):
        return principal.client_id
    return fallback


_PASSWORD_ALGORITHM = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 310_000
_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$310000$YXV0aC1kdW1teS1zYWx0$"
    "3B0mbQO_8XxrKOBvWvl16fskH70p6w1gCtH1VoTbofM"
)


def _is_supported_password_hash(value: str) -> bool:
    try:
        algorithm, iterations, salt, digest = value.split("$", 3)
        return (
            algorithm == _PASSWORD_ALGORITHM
            and int(iterations) >= _PASSWORD_ITERATIONS
            and bool(_b64url_decode(salt))
            and len(_b64url_decode(digest)) == hashlib.sha256().digest_size
        )
    except (TypeError, ValueError):
        return False


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    password_salt = salt if salt is not None else os.urandom(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt,
        _PASSWORD_ITERATIONS,
    )
    return "$".join(
        (
            _PASSWORD_ALGORITHM,
            str(_PASSWORD_ITERATIONS),
            _b64url_encode(password_salt),
            _b64url_encode(digest),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    if not _is_supported_password_hash(encoded_hash):
        return False
    _, raw_iterations, raw_salt, raw_digest = encoded_hash.split("$", 3)
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _b64url_decode(raw_salt),
        int(raw_iterations),
    )
    return hmac.compare_digest(candidate, _b64url_decode(raw_digest))


__all__ = [
    "AuthPrincipal",
    "AuthSettings",
    "AuthUser",
    "AuthenticationMiddleware",
    "SessionAuthenticator",
    "authenticated_client_id",
    "create_auth_router",
    "hash_password",
    "verify_password",
]
