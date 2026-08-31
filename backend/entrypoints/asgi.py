"""ASGI process entrypoint."""

from __future__ import annotations

from backend.bootstrap.http import create_app, register_global_exception_handlers

app = create_app()


def main() -> None:
    """Run the local development ASGI server."""

    import uvicorn

    uvicorn.run(
        "backend.entrypoints.asgi:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
    )


if __name__ == "__main__":
    main()


__all__ = ["app", "create_app", "main", "register_global_exception_handlers"]
