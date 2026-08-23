"""Process-scoped OpenAI SDK client and connection-pool ownership."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import httpx
from openai import OpenAI


def project_env_value(name: str) -> str | None:
    """Read a project setting from the environment or the repository ``.env``."""
    value = os.getenv(name)
    if value:
        return value
    for parent in Path(__file__).resolve().parents:
        candidate_env = parent / ".env"
        if candidate_env.is_file():
            break
    else:
        return None
    for raw_line in candidate_env.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, candidate = line.split("=", 1)
        if key.strip() == name:
            return candidate.strip().strip('"').strip("'") or None
    return None


class OpenAIProviderError(RuntimeError):
    """Raised when the shared OpenAI provider is not configured."""


class OpenAIProvider:
    """Own the official SDK client and its reusable HTTP connection pool."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or project_env_value("OPENAI_API_KEY")
        self.base_url = (
            base_url
            or project_env_value("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
            ),
        )
        self._client: OpenAI | None = None
        self._client_lock = threading.Lock()

    @property
    def client(self) -> OpenAI:
        """Return the lazily initialized official SDK client."""
        if not self.api_key:
            raise OpenAIProviderError("OPENAI_API_KEY가 설정되지 않았습니다")
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is None:
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    max_retries=self.max_retries,
                    http_client=self._http_client,
                )
            return self._client

    def with_timeout(self, timeout_seconds: float | None = None) -> OpenAI:
        client = self.client
        if timeout_seconds is None or timeout_seconds == self.timeout_seconds:
            return client
        return client.with_options(timeout=timeout_seconds)

    def close(self) -> None:
        """Close only the HTTP pool created by this provider."""
        if self._owns_http_client:
            self._http_client.close()


__all__ = [
    "OpenAIProvider",
    "OpenAIProviderError",
    "project_env_value",
]
