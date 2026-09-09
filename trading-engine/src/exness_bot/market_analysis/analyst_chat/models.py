"""Typed models for Phase 16.3.5 AI Market Analyst Chat — analysis only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "1.0"


class AnswerType(StrEnum):
    TECHNICAL_EXPLANATION = "TECHNICAL_EXPLANATION"
    EXTERNAL_EXPLANATION = "EXTERNAL_EXPLANATION"
    SYNTHESIS_EXPLANATION = "SYNTHESIS_EXPLANATION"
    BOT_SIGNAL_EXPLANATION = "BOT_SIGNAL_EXPLANATION"
    RISK_EXPLANATION = "RISK_EXPLANATION"
    GENERAL_MARKET_QUESTION = "GENERAL_MARKET_QUESTION"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    READ_ONLY_REFUSAL = "READ_ONLY_REFUSAL"


class ChatIntent(StrEnum):
    WHY_BOT_SIGNAL = "WHY_BOT_SIGNAL"
    CURRENT_PRICE = "CURRENT_PRICE"
    TECHNICAL_STATE = "TECHNICAL_STATE"
    TIMEFRAME_CONFLICT = "TIMEFRAME_CONFLICT"
    SUPPORT_RESISTANCE = "SUPPORT_RESISTANCE"
    EXTERNAL_CONTEXT = "EXTERNAL_CONTEXT"
    EVENT_RISK = "EVENT_RISK"
    WHAT_TO_WATCH = "WHAT_TO_WATCH"
    EXECUTION_REQUEST = "EXECUTION_REQUEST"
    GENERAL = "GENERAL"


def _json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, StrEnum):
        return str(obj.value)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return _json_safe(asdict(obj))
    return obj


def _as_dict(payload: dict[str, Any]) -> dict[str, Any]:
    result = _json_safe(payload)
    return result if isinstance(result, dict) else {}


@dataclass
class SourceRef:
    source_id: str
    title: str
    domain: str
    url: str
    freshness: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class UsedContext:
    technical: bool = False
    external: bool = False
    synthesis: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class ProviderMetadata:
    provider: str | None
    model: str | None
    used: bool
    fallback_used: bool
    latency_ms: float | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class MarketAnalystContext:
    schema_version: str
    symbol: str
    generated_at: str
    technical_fingerprint: str | None
    external_fingerprint: str | None
    synthesis_fingerprint: str | None
    technical: dict[str, Any]
    external: dict[str, Any]
    synthesis: dict[str, Any]
    sources: list[SourceRef]
    freshness: dict[str, Any]
    context_status: str

    def to_compact_prompt(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "context_status": self.context_status,
            "technical": self.technical,
            "external": self.external,
            "synthesis": self.synthesis,
            "freshness": self.freshness,
            "source_summaries": [
                {
                    "source_id": s.source_id,
                    "title": s.title,
                    "domain": s.domain,
                    "freshness": s.freshness,
                }
                for s in self.sources[:12]
            ],
            "fingerprints": {
                "technical": self.technical_fingerprint,
                "external": self.external_fingerprint,
                "synthesis": self.synthesis_fingerprint,
            },
        }


@dataclass
class ChatMessage:
    role: str
    content: str
    created_at: str
    message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class MarketAnalystChatResponse:
    schema_version: str
    message_id: str
    session_id: str
    symbol: str
    created_at: str
    answer: str
    answer_type: str
    intent: str
    context_status: str
    context_changed: bool
    used_context: UsedContext
    technical_fingerprint: str | None
    external_fingerprint: str | None
    synthesis_fingerprint: str | None
    source_refs: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_metadata: ProviderMetadata = field(
        default_factory=lambda: ProviderMetadata(
            provider=None, model=None, used=False, fallback_used=True
        )
    )
    note: str = (
        "AI Market Analyst cannot execute or approve trades. "
        "Analysis / explanation only."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "session_id": self.session_id,
            "symbol": self.symbol,
            "created_at": self.created_at,
            "answer": self.answer,
            "answer_type": self.answer_type,
            "intent": self.intent,
            "context_status": self.context_status,
            "context_changed": self.context_changed,
            "used_context": self.used_context.to_dict(),
            "technical_fingerprint": self.technical_fingerprint,
            "external_fingerprint": self.external_fingerprint,
            "synthesis_fingerprint": self.synthesis_fingerprint,
            "source_refs": list(self.source_refs),
            "sources": [s.to_dict() for s in self.sources],
            "warnings": list(self.warnings),
            "provider_metadata": self.provider_metadata.to_dict(),
            "note": self.note,
        }
