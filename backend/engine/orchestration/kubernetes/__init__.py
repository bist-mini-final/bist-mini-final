"""PostgreSQL queue boundary consumed by KEDA Kubernetes Jobs."""

from .dispatcher import KubernetesQueueDispatcher

__all__ = ["KubernetesQueueDispatcher"]
