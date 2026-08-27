"""HTTP observability middleware for the presentation layer."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.api.versioning import API_V1_PREFIX, LEGACY_API_PREFIX

logger = logging.getLogger("backend.api.middleware")


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Attach request correlation and server processing-time headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started_at = time.perf_counter()
        response = await call_next(request)
        process_time_ms = (time.perf_counter() - started_at) * 1000.0

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
        path = request.url.path
        if path == LEGACY_API_PREFIX or (
            path.startswith(f"{LEGACY_API_PREFIX}/")
            and path != API_V1_PREFIX
            and not path.startswith(f"{API_V1_PREFIX}/")
        ):
            successor = f"{API_V1_PREFIX}{path[len(LEGACY_API_PREFIX):]}"
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = f'<{successor}>; rel="successor-version"'
        if process_time_ms > 1000.0 and path.startswith("/api/"):
            logger.warning(
                "Slow request: %s %s [%s] took %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                process_time_ms,
            )
        return response


__all__ = ["RequestObservabilityMiddleware"]
