"""Lightweight JSONL session store for analyst chat."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.analyst_chat.models import ChatMessage


def default_chat_data_root() -> Path:
    cwd = Path.cwd()
    candidate = cwd / "data" / "analyst_chat"
    if (cwd / "data").exists() or candidate.parent.exists():
        return candidate
    engine_root = Path(__file__).resolve().parents[4]
    return engine_root / "data" / "analyst_chat"


@dataclass
class ChatSession:
    session_id: str
    symbol: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = field(default_factory=list)
    last_technical_fp: str | None = None
    last_external_fp: str | None = None
    last_synthesis_fp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "symbol": self.symbol,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
            "last_technical_fp": self.last_technical_fp,
            "last_external_fp": self.last_external_fp,
            "last_synthesis_fp": self.last_synthesis_fp,
        }


class ChatSessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or default_chat_data_root()
        self._root.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, ChatSession] = {}

    def _path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:80]
        return self._root / f"{safe}.json"

    def create(self, symbol: str) -> ChatSession:
        now = datetime.now(tz=UTC).isoformat()
        session = ChatSession(
            session_id=str(uuid.uuid4()),
            symbol=symbol.strip().upper(),
            created_at=now,
            updated_at=now,
        )
        self._memory[session.session_id] = session
        self._persist(session)
        return session

    def get(self, session_id: str) -> ChatSession | None:
        if session_id in self._memory:
            return self._memory[session_id]
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        messages = [
            ChatMessage(
                role=str(m.get("role") or "user"),
                content=str(m.get("content") or ""),
                created_at=str(m.get("created_at") or ""),
                message_id=m.get("message_id"),
            )
            for m in data.get("messages") or []
            if isinstance(m, dict)
        ]
        session = ChatSession(
            session_id=str(data.get("session_id") or session_id),
            symbol=str(data.get("symbol") or "").upper(),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            messages=messages,
            last_technical_fp=data.get("last_technical_fp"),
            last_external_fp=data.get("last_external_fp"),
            last_synthesis_fp=data.get("last_synthesis_fp"),
        )
        self._memory[session.session_id] = session
        return session

    def save(self, session: ChatSession) -> None:
        session.updated_at = datetime.now(tz=UTC).isoformat()
        self._memory[session.session_id] = session
        self._persist(session)

    def _persist(self, session: ChatSession) -> None:
        path = self._path(session.session_id)
        try:
            path.write_text(
                json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
