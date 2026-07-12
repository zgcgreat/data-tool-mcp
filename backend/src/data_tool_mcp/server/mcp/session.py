"""SSE session manager — manages SSE sessions with event queues and cleanup.

Maps to Go: internal/server/mcp.go sseSession / sseManager
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any


class SSESession:
    """A single SSE session.

    Maps to Go: sseSession struct
    """

    def __init__(self) -> None:
        self.id: str = uuid.uuid4().hex
        self.done: asyncio.Event = asyncio.Event()
        self.event_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self.last_active: float = time.monotonic()
        self.protocol_version: str = "2024-11-05"
        self.toolset_name: str = ""

    def touch(self) -> None:
        """Update last active timestamp. Maps to Go: session.lastActive = time.Now()"""
        self.last_active = time.monotonic()

    def close(self) -> None:
        """Signal the session is done."""
        self.done.set()


class SSEManager:
    """Manages SSE sessions with thread-safe access and periodic cleanup.

    Maps to Go: sseManager struct with mutex + cleanupRoutine
    """

    def __init__(self, timeout: float = 600.0) -> None:
        self._sessions: dict[str, SSESession] = {}
        self._lock = asyncio.Lock()
        self._timeout = timeout
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the cleanup routine. Maps to Go: go sseM.cleanupRoutine(ctx)"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_routine())

    async def stop(self) -> None:
        """Stop the cleanup routine and close all sessions."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        async with self._lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()

    async def add(self, session: SSESession) -> None:
        """Register a new session. Maps to Go: m.add(id, session)"""
        async with self._lock:
            self._sessions[session.id] = session

    async def get(self, session_id: str) -> SSESession | None:
        """Look up a session by ID. Maps to Go: m.get(id)"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.touch()
            return session

    async def remove(self, session_id: str) -> None:
        """Remove a session. Maps to Go: m.remove(id)"""
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def _cleanup_routine(self) -> None:
        """Periodically remove stale sessions. Maps to Go: cleanupRoutine"""
        try:
            while True:
                await asyncio.sleep(self._timeout)
                now = time.monotonic()
                async with self._lock:
                    stale = [
                        sid
                        for sid, sess in self._sessions.items()
                        if now - sess.last_active > self._timeout
                    ]
                    for sid in stale:
                        self._sessions[sid].close()
                        del self._sessions[sid]
        except asyncio.CancelledError:
            return
