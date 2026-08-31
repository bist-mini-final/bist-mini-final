"""Kubernetes-backed workflow dispatch adapters."""

from .dispatcher import KubernetesQueueDispatcher

__all__ = ["KubernetesQueueDispatcher"]
