"""
Lightweight in-memory chat history per user + session (or analysis-scoped session).

Thread-safe. Not durable across process restarts — sufficient for demo/production single-instance;
swap for Redis if you scale horizontally.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Dict, List, Literal, Optional

Role = Literal["user", "assistant"]

_MAX_DEFAULT = 10


class ChatMemoryService:
    def __init__(self, max_turns: int = _MAX_DEFAULT) -> None:
        self._max = max(2, min(30, max_turns))
        self._lock = threading.Lock()
        # key -> deque of {"role", "content"}
        self._store: Dict[str, Deque[dict]] = {}

    def _key(self, user_id: int, session_id: Optional[str], analysis_id: Optional[int]) -> str:
        sid = (session_id or "").strip() or "default"
        if analysis_id is not None:
            return f"u:{user_id}:a:{analysis_id}:s:{sid}"
        return f"u:{user_id}:s:{sid}"

    def append(self, user_id: int, *, session_id: Optional[str], analysis_id: Optional[int], role: Role, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        key = self._key(user_id, session_id, analysis_id)
        with self._lock:
            dq = self._store.get(key)
            if dq is None:
                dq = deque(maxlen=self._max * 2)
                self._store[key] = dq
            dq.append({"role": role, "content": text[:12000]})

    def get_recent(
        self,
        user_id: int,
        *,
        session_id: Optional[str],
        analysis_id: Optional[int],
        max_messages: Optional[int] = None,
    ) -> List[dict]:
        key = self._key(user_id, session_id, analysis_id)
        cap = max_messages or (self._max * 2)
        with self._lock:
            dq = self._store.get(key)
            if not dq:
                return []
            items = list(dq)[-cap:]
            return [{"role": m["role"], "content": m["content"]} for m in items]


_memory_singleton: Optional[ChatMemoryService] = None
_memory_lock = threading.Lock()


def get_chat_memory() -> ChatMemoryService:
    global _memory_singleton
    from app.config import get_settings

    s = get_settings()
    mt = int(s.chat_memory_max_turns)
    with _memory_lock:
        if _memory_singleton is None:
            _memory_singleton = ChatMemoryService(max_turns=mt)
        return _memory_singleton
