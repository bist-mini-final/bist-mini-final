"""Compatibility imports for the former composition-root module.

New code imports :mod:`backend.bootstrap.application`.  This module remains
temporarily so external scripts can migrate without changing runtime behavior.
"""

from backend.bootstrap.application import (
    ApplicationContainer,
    DomainServicesContainer,
    ExecutionContainer,
    RuntimeContainer,
    RuntimePaths,
)

__all__ = [
    "ApplicationContainer",
    "DomainServicesContainer",
    "ExecutionContainer",
    "RuntimeContainer",
    "RuntimePaths",
]
