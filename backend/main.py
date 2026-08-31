"""Compatibility ASGI import; use :mod:`backend.entrypoints.asgi`."""

from backend.entrypoints.asgi import (
    app,
    create_app,
    main,
    register_global_exception_handlers,
)

if __name__ == "__main__":
    main()

__all__ = ["app", "create_app", "main", "register_global_exception_handlers"]
