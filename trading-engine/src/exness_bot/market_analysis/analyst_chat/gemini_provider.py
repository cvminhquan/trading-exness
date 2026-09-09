"""Gemini provider for Market Analyst Chat — plain generation, no tools."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import structlog

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.analyst_chat.models import (
    ChatMessage,
    MarketAnalystContext,
)
from exness_bot.market_analysis.analyst_chat.prompt_builder import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from exness_bot.market_analysis.analyst_chat.provider_base import (
    MarketAnalystProviderResponse,
)

logger = structlog.get_logger(__name__)

_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = _JSON_RE.search(raw)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


class GeminiMarketAnalystProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def answer(
        self,
        *,
        context: MarketAnalystContext,
        conversation: list[ChatMessage],
        message: str,
    ) -> MarketAnalystProviderResponse:
        started = time.perf_counter()
        model = self._settings.ai_market_analyst_chat_model
        api_key = (self._settings.gemini_api_key or "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")

        user_prompt = build_user_prompt(
            context=context, message=message, history=conversation
        )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai not installed; install optional [ai] extras"
            ) from exc

        client = genai.Client(api_key=api_key)
        timeout = float(self._settings.ai_market_analyst_chat_timeout_seconds)
        # Plain generation — no Google Search, no function/tool calling.
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        text = getattr(response, "text", None) or ""
        parsed = _parse_json_blob(text)
        if parsed is None:
            return MarketAnalystProviderResponse(
                answer=text.strip()[:4000] or "Empty provider response",
                answer_type="GENERAL_MARKET_QUESTION",
                provider="gemini",
                model=model,
                latency_ms=latency_ms,
            )
        answer = str(parsed.get("answer") or "").strip()
        answer_type = str(
            parsed.get("answer_type") or "GENERAL_MARKET_QUESTION"
        ).strip()
        refs_raw = parsed.get("source_refs") or []
        refs = [str(r) for r in refs_raw if isinstance(r, (str, int))]
        warnings = [
            str(w) for w in (parsed.get("warnings") or []) if w is not None
        ]
        _ = timeout  # reserved for future client timeout wiring
        logger.info(
            "analyst_chat_gemini_ok",
            symbol=context.symbol,
            model=model,
            latency_ms=round(latency_ms, 1),
            source_ref_count=len(refs),
        )
        return MarketAnalystProviderResponse(
            answer=answer or text.strip()[:4000],
            answer_type=answer_type,
            source_refs=refs,
            warnings=warnings,
            provider="gemini",
            model=model,
            latency_ms=latency_ms,
        )
