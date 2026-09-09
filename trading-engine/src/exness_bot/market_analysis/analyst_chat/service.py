"""MarketAnalystChatService — context-aware read-only analysis chat."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.analyst_chat.context_builder import (
    MarketAnalystContextBuilder,
)
from exness_bot.market_analysis.analyst_chat.fallback import build_fallback_answer
from exness_bot.market_analysis.analyst_chat.fake_provider import (
    FakeMarketAnalystProvider,
)
from exness_bot.market_analysis.analyst_chat.gemini_provider import (
    GeminiMarketAnalystProvider,
)
from exness_bot.market_analysis.analyst_chat.intent import classify_intent
from exness_bot.market_analysis.analyst_chat.models import (
    SCHEMA_VERSION,
    AnswerType,
    ChatIntent,
    ChatMessage,
    MarketAnalystChatResponse,
    ProviderMetadata,
    UsedContext,
)
from exness_bot.market_analysis.analyst_chat.provider_base import (
    MarketAnalystProvider,
)
from exness_bot.market_analysis.analyst_chat.rate_limit import ChatRateLimiter
from exness_bot.market_analysis.analyst_chat.session import (
    ChatSession,
    ChatSessionStore,
)
from exness_bot.market_analysis.analyst_chat.validator import (
    ValidationError,
    validate_provider_response,
)

logger = structlog.get_logger(__name__)

_SECRETISH = re.compile(
    r"(?i)(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S+"
)


def _redact(text: str) -> str:
    return _SECRETISH.sub(r"\1=[REDACTED]", text)


class MarketAnalystChatService:
    def __init__(
        self,
        settings: Settings,
        *,
        context_builder: MarketAnalystContextBuilder | None = None,
        provider: MarketAnalystProvider | None = None,
        session_store: ChatSessionStore | None = None,
        rate_limiter: ChatRateLimiter | None = None,
        data_source: Any | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._builder = context_builder or MarketAnalystContextBuilder(
            settings, data_source=data_source
        )
        self._provider = provider
        self._sessions = session_store or ChatSessionStore()
        self._rate = rate_limiter or ChatRateLimiter(
            max_requests=settings.ai_market_analyst_chat_rate_limit,
            window_seconds=60.0,
        )
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def _resolve_provider(self) -> MarketAnalystProvider | None:
        if self._provider is not None:
            return self._provider
        if not self._settings.ai_market_analyst_chat_enabled:
            return None
        name = (
            self._settings.ai_market_analyst_chat_provider or "gemini"
        ).strip().lower()
        if name == "fake":
            return FakeMarketAnalystProvider()
        return GeminiMarketAnalystProvider(self._settings)

    def _used_context_for_intent(self, intent: ChatIntent) -> UsedContext:
        if intent is ChatIntent.WHY_BOT_SIGNAL:
            return UsedContext(technical=True, external=True, synthesis=True)
        if intent in {
            ChatIntent.CURRENT_PRICE,
            ChatIntent.TECHNICAL_STATE,
            ChatIntent.TIMEFRAME_CONFLICT,
            ChatIntent.SUPPORT_RESISTANCE,
        }:
            return UsedContext(technical=True, external=False, synthesis=False)
        if intent in {ChatIntent.EXTERNAL_CONTEXT, ChatIntent.EVENT_RISK}:
            return UsedContext(technical=True, external=True, synthesis=False)
        if intent is ChatIntent.WHAT_TO_WATCH:
            return UsedContext(technical=True, external=True, synthesis=True)
        return UsedContext(technical=True, external=True, synthesis=True)

    def _ensure_session(
        self, *, symbol: str, session_id: str | None
    ) -> ChatSession:
        if session_id:
            existing = self._sessions.get(session_id)
            if existing is not None:
                if existing.symbol != symbol:
                    # Symbol isolation — start a new session
                    return self._sessions.create(symbol)
                return existing
        return self._sessions.create(symbol)

    def chat(
        self,
        *,
        symbol: str,
        message: str,
        session_id: str | None = None,
    ) -> MarketAnalystChatResponse:
        canonical = symbol.strip().upper() or "XAUUSD"
        now = self._clock()
        now_iso = now.isoformat()
        msg = (message or "").strip()
        max_len = self._settings.ai_market_analyst_chat_max_message_length
        if not msg:
            raise ValueError("message_required")
        if len(msg) > max_len:
            raise ValueError("message_too_long")

        if not self._rate.allow(f"chat:{canonical}"):
            raise RuntimeError("rate_limited")

        intent = classify_intent(msg)
        context = self._builder.build(canonical)
        session = self._ensure_session(symbol=canonical, session_id=session_id)
        max_hist = self._settings.ai_market_analyst_chat_max_history_messages
        history = list(session.messages[-max_hist:])

        context_changed = False
        if session.last_technical_fp is not None:
            context_changed = (
                session.last_technical_fp != context.technical_fingerprint
                or session.last_external_fp != context.external_fingerprint
                or session.last_synthesis_fp != context.synthesis_fingerprint
            )

        message_id = str(uuid.uuid4())
        warnings: list[str] = []
        fallback_used = True
        provider_meta = ProviderMetadata(
            provider=None, model=None, used=False, fallback_used=True
        )

        # Disabled AI → deterministic only (clean UX, not crash)
        provider = self._resolve_provider()
        answer_text = ""
        answer_type = AnswerType.GENERAL_MARKET_QUESTION.value
        source_refs: list[str] = []
        sources = []

        if intent is ChatIntent.EXECUTION_REQUEST or provider is None:
            answer_text, atype, source_refs = build_fallback_answer(
                intent=intent, context=context
            )
            answer_type = atype.value
            sources = [
                s for s in context.sources if s.source_id in source_refs
            ]
            if provider is None and intent is not ChatIntent.EXECUTION_REQUEST:
                if not self._settings.ai_market_analyst_chat_enabled:
                    warnings.append("ai_chat_disabled")
                else:
                    warnings.append("ai_provider_unavailable")
        else:
            try:
                raw = provider.answer(
                    context=context, conversation=history, message=msg
                )
                try:
                    (
                        answer_text,
                        answer_type,
                        source_refs,
                        sources,
                        v_warnings,
                    ) = validate_provider_response(raw, context=context)
                    warnings.extend(v_warnings)
                    fallback_used = False
                    provider_meta = ProviderMetadata(
                        provider=raw.provider,
                        model=raw.model,
                        used=True,
                        fallback_used=False,
                        latency_ms=raw.latency_ms,
                    )
                except ValidationError as ve:
                    warnings.append(f"provider_rejected:{ve.reason}")
                    answer_text, atype, source_refs = build_fallback_answer(
                        intent=intent, context=context
                    )
                    answer_type = atype.value
                    sources = [
                        s for s in context.sources if s.source_id in source_refs
                    ]
                    provider_meta = ProviderMetadata(
                        provider=raw.provider,
                        model=raw.model,
                        used=True,
                        fallback_used=True,
                        latency_ms=raw.latency_ms,
                        error_type=ve.reason,
                    )
            except Exception as exc:  # noqa: BLE001 — provider isolation
                warnings.append("provider_failure")
                logger.warning(
                    "analyst_chat_provider_failed",
                    symbol=canonical,
                    error_type=type(exc).__name__,
                )
                answer_text, atype, source_refs = build_fallback_answer(
                    intent=intent, context=context
                )
                answer_type = atype.value
                sources = [
                    s for s in context.sources if s.source_id in source_refs
                ]
                provider_meta = ProviderMetadata(
                    provider=getattr(provider, "__class__", type(provider)).__name__,
                    model=self._settings.ai_market_analyst_chat_model,
                    used=False,
                    fallback_used=True,
                    error_type=type(exc).__name__,
                )

        # Freshness warnings
        tech_fresh = context.freshness.get("technical")
        if isinstance(tech_fresh, dict) and str(tech_fresh.get("status")).upper() == "STALE":
            warnings.append("technical_stale")
        ext_fresh = context.freshness.get("external")
        if isinstance(ext_fresh, dict) and str(ext_fresh.get("status")).upper() == "STALE":
            warnings.append("external_stale")
        elif str(context.external.get("status") or "").upper() in {
            "STALE",
            "UNAVAILABLE",
            "DISABLED",
        }:
            if str(context.external.get("status")).upper() == "STALE":
                warnings.append("external_stale")

        used = self._used_context_for_intent(intent)

        # Persist session turn
        session.messages.append(
            ChatMessage(
                role="user",
                content=_redact(msg)[:max_len],
                created_at=now_iso,
                message_id=None,
            )
        )
        session.messages.append(
            ChatMessage(
                role="assistant",
                content=answer_text,
                created_at=now_iso,
                message_id=message_id,
            )
        )
        # Bound stored history
        if len(session.messages) > max_hist * 2:
            session.messages = session.messages[-(max_hist * 2) :]
        session.last_technical_fp = context.technical_fingerprint
        session.last_external_fp = context.external_fingerprint
        session.last_synthesis_fp = context.synthesis_fingerprint
        self._sessions.save(session)

        logger.info(
            "analyst_chat_answered",
            session_id=session.session_id,
            symbol=canonical,
            intent=intent.value,
            answer_type=answer_type,
            fallback_used=fallback_used or provider_meta.fallback_used,
            provider=provider_meta.provider,
            model=provider_meta.model,
            context_changed=context_changed,
            technical_fp=context.technical_fingerprint,
            external_fp=context.external_fingerprint,
            synthesis_fp=context.synthesis_fingerprint,
            source_count=len(sources),
        )

        return MarketAnalystChatResponse(
            schema_version=SCHEMA_VERSION,
            message_id=message_id,
            session_id=session.session_id,
            symbol=canonical,
            created_at=now_iso,
            answer=answer_text,
            answer_type=answer_type,
            intent=intent.value,
            context_status=context.context_status,
            context_changed=context_changed,
            used_context=used,
            technical_fingerprint=context.technical_fingerprint,
            external_fingerprint=context.external_fingerprint,
            synthesis_fingerprint=context.synthesis_fingerprint,
            source_refs=source_refs,
            sources=sources,
            warnings=list(dict.fromkeys(warnings)),
            provider_metadata=provider_meta,
        )
