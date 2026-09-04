"""Diagnostics package with lightweight server-event exports."""

from face_moment.diagnostics.server_events import (
    EVENT_CATALOG,
    EVENT_QUEUE_CAPACITY,
    SERVER_EVENT_SEARCH_LIMIT,
    ServerEvent,
    ServerEventCode,
    ServerEventEmitter,
    ServerEventProjection,
    ServerEventRepository,
    ServerEventSearchFilters,
    ServerEventSink,
)

__all__ = [
    "EVENT_CATALOG",
    "EVENT_QUEUE_CAPACITY",
    "SERVER_EVENT_SEARCH_LIMIT",
    "ServerEvent",
    "ServerEventCode",
    "ServerEventEmitter",
    "ServerEventProjection",
    "ServerEventRepository",
    "ServerEventSearchFilters",
    "ServerEventSink",
]
