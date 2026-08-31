"""Compatibility imports for :mod:`backend.platform.redis.state_stream_broker`."""

from backend.platform.redis.state_stream_broker import (
    RedisStateStreamBroker,
    create_state_stream_broker,
)
from backend.shared.application.state_stream_broker import StateStreamBroker

__all__ = [
    "RedisStateStreamBroker",
    "StateStreamBroker",
    "create_state_stream_broker",
]
