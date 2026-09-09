"""Gemini provider for synthesis narrative — NO Google Search / tools."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from exness_bot.market_analysis.synthesis.models import MarketSynthesisNarrative
from exness_bot.market_analysis.synthesis.prompt_builder import (
    SYSTEM_INSTRUCTIONS,
    build_user_prompt,
)
from exness_bot.market_analysis.synthesis.provider_base import (
    MarketSynthesisPromptInput,
    MarketSynthesisProviderResult,
)

logger = structlog.get_logger(__name__)


def _parse_json(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None


class GeminiMarketSynthesisProvider:
    """Live Gemini narrative provider — tools disabled (no web search)."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds

    def generate_explanation(
        self, request: MarketSynthesisPromptInput
    ) -> MarketSynthesisProviderResult:
        started = time.perf_counter()
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return MarketSynthesisProviderResult(
                ok=False,
                error_type="ImportError",
                latency_ms=(time.perf_counter() - started) * 1000,
                provider=self.name,
                model=self.model,
            )

        if not self._api_key.strip():
            return MarketSynthesisProviderResult(
                ok=False,
                error_type="missing_api_key",
                latency_ms=(time.perf_counter() - started) * 1000,
                provider=self.name,
                model=self.model,
            )

        client = genai.Client(api_key=self._api_key)
        user = build_user_prompt(request.payload)
        try:
            # Explicitly NO tools — Phase 16.3.3 must not search the web.
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTIONS,
                temperature=0.2,
            )
            response = client.models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )
        except Exception as exc:
            logger.warning(
                "gemini_synthesis_failed",
                error=type(exc).__name__,
                model=self.model,
            )
            return MarketSynthesisProviderResult(
                ok=False,
                error_type=type(exc).__name__,
                latency_ms=(time.perf_counter() - started) * 1000,
                provider=self.name,
                model=self.model,
            )

        text = getattr(response, "text", None) or ""
        payload = _parse_json(text)
        latency = (time.perf_counter() - started) * 1000
        if not payload:
            return MarketSynthesisProviderResult(
                ok=False,
                error_type="invalid_json",
                latency_ms=latency,
                provider=self.name,
                model=self.model,
                raw={"text_preview": text[:500]},
            )

        narrative = MarketSynthesisNarrative(
            summary=str(payload.get("summary") or ""),
            technical_explanation=str(payload.get("technical_explanation") or ""),
            external_explanation=str(payload.get("external_explanation") or ""),
            alignment_explanation=str(payload.get("alignment_explanation") or ""),
            risk_explanation=str(payload.get("risk_explanation") or ""),
            uncertainties=[
                str(x) for x in (payload.get("uncertainties") or []) if x
            ][:8],
            what_to_watch=[
                str(x) for x in (payload.get("what_to_watch") or []) if x
            ][:8],
        )
        logger.info(
            "gemini_synthesis_ok",
            model=self.model,
            symbol=request.symbol,
            latency_ms=round(latency, 1),
        )
        return MarketSynthesisProviderResult(
            ok=True,
            narrative=narrative,
            raw=payload,
            latency_ms=latency,
            provider=self.name,
            model=self.model,
        )
