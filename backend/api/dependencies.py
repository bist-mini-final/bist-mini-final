"""Request-scoped FastAPI dependency providers.

Only this presentation-layer module knows that the application container is
stored on ``app.state``. Route modules depend on typed providers instead of
reaching into framework state themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.bootstrap.application import ApplicationContainer
from backend.bootstrap.module_registry import ModuleRegistry
from backend.bootstrap.runtime import WorkflowRuntimeServices
from backend.domains.bi.application import BiApiServices


def get_container(request: Request) -> ApplicationContainer:
    """Return the process-owned composition root for the current request."""

    container = getattr(request.app.state, "container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("애플리케이션 컨테이너가 초기화되지 않았습니다")
    return container


ContainerDependency = Annotated[ApplicationContainer, Depends(get_container)]


def get_runtime_services(container: ContainerDependency) -> WorkflowRuntimeServices:
    return container.runtime.services


RuntimeServicesDependency = Annotated[
    WorkflowRuntimeServices,
    Depends(get_runtime_services),
]


def get_module_registry(services: RuntimeServicesDependency) -> ModuleRegistry:
    return services.module_registry


def get_bi_services(container: ContainerDependency) -> BiApiServices:
    return container.domain.bi_services


BiServicesDependency = Annotated[BiApiServices, Depends(get_bi_services)]

__all__ = [
    "BiServicesDependency",
    "ContainerDependency",
    "RuntimeServicesDependency",
    "get_bi_services",
    "get_container",
    "get_module_registry",
    "get_runtime_services",
]
