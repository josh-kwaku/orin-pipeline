"""
Server-Sent Events (SSE) manager for real-time updates.
"""

import asyncio
import json
from typing import Any


class EventManager:
    """
    Manages SSE subscriptions and broadcasts events to all connected clients.

    Uses asyncio.Queue for each subscriber to handle backpressure.
    """

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to events.

        Returns:
            Queue that will receive events
        """
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.append(queue)
        print(f"[SSE] New subscriber. Total: {len(self._subscribers)}")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        Unsubscribe from events.

        Args:
            queue: The queue returned from subscribe()
        """
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Emit an event to all subscribers.

        Args:
            event_type: Type of event (e.g., "track_start", "track_complete")
            data: Event payload
        """
        event = {
            "type": event_type,
            "data": data,
        }

        print(f"[SSE] Emitting {event_type} to {len(self._subscribers)} subscribers")

        async with self._lock:
            for queue in self._subscribers:
                try:
                    # Non-blocking put, drop if queue is full
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Client is too slow, skip this event
                    pass

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self._subscribers)


# Global event manager instance
event_manager = EventManager()
