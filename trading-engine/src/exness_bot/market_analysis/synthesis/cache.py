"""File + memory cache for MarketSynthesis."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    fingerprint: str
    provider: str
    model: str
    generated_at: datetime
    expires_at: datetime
    payload: dict[str, Any]


class SynthesisCache:
    def __init__(self, *, root: Path, ttl_seconds: int) -> None:
        self._root = root
        self._ttl = max(1, ttl_seconds)
        self._memory: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._root.mkdir(parents=True, exist_ok=True)

    def _key(self, symbol: str, provider: str, model: str, fingerprint: str) -> str:
        return f"{symbol}|{provider}|{model}|{fingerprint}"

    def _path(self, symbol: str) -> Path:
        return self._root / f"{symbol.upper()}_market_synthesis_cache.json"

    def get(
        self,
        *,
        symbol: str,
        provider: str,
        model: str,
        fingerprint: str,
        now: datetime,
    ) -> tuple[dict[str, Any] | None, float | None, str | None]:
        key = self._key(symbol, provider, model, fingerprint)
        with self._lock:
            entry = self._memory.get(key)
            if entry is None:
                entry = self._load_disk(symbol, provider, model, fingerprint)
                if entry is not None:
                    self._memory[key] = entry
            if entry is None or now >= entry.expires_at:
                return None, None, None
            age = (now - entry.generated_at).total_seconds()
            return entry.payload, age, entry.expires_at.isoformat()

    def put(
        self,
        *,
        symbol: str,
        provider: str,
        model: str,
        fingerprint: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> CacheEntry:
        expires = now + timedelta(seconds=self._ttl)
        entry = CacheEntry(
            fingerprint=fingerprint,
            provider=provider,
            model=model,
            generated_at=now,
            expires_at=expires,
            payload=payload,
        )
        key = self._key(symbol, provider, model, fingerprint)
        with self._lock:
            self._memory[key] = entry
            path = self._path(symbol)
            path.write_text(
                json.dumps(
                    {
                        "fingerprint": fingerprint,
                        "provider": provider,
                        "model": model,
                        "generated_at": now.isoformat(),
                        "expires_at": expires.isoformat(),
                        "payload": payload,
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            hist = self._root / f"{symbol.upper()}_market_synthesis_history.jsonl"
            with hist.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "generated_at": now.isoformat(),
                            "symbol": symbol,
                            "fingerprint": fingerprint,
                            "provider": provider,
                            "model": model,
                            "status": payload.get("status"),
                            "synthesis_state": (payload.get("synthesis") or {}).get(
                                "state"
                            ),
                        },
                        default=str,
                    )
                    + "\n"
                )
        return entry

    def _load_disk(
        self,
        symbol: str,
        provider: str,
        model: str,
        fingerprint: str,
    ) -> CacheEntry | None:
        path = self._path(symbol)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            raw.get("fingerprint") != fingerprint
            or raw.get("provider") != provider
            or raw.get("model") != model
        ):
            return None
        try:
            generated = datetime.fromisoformat(str(raw["generated_at"]))
            expires = datetime.fromisoformat(str(raw["expires_at"]))
        except (KeyError, ValueError):
            return None
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=UTC)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            return None
        return CacheEntry(
            fingerprint=fingerprint,
            provider=provider,
            model=model,
            generated_at=generated,
            expires_at=expires,
            payload=payload,
        )
