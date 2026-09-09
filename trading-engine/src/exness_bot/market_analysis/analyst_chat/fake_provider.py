"""Fake provider for deterministic unit tests."""

from __future__ import annotations

from exness_bot.market_analysis.analyst_chat.models import (
    ChatMessage,
    MarketAnalystContext,
)
from exness_bot.market_analysis.analyst_chat.provider_base import (
    MarketAnalystProviderResponse,
)


class FakeMarketAnalystProvider:
    def __init__(
        self,
        *,
        answer: str | None = None,
        answer_type: str = "GENERAL_MARKET_QUESTION",
        source_refs: list[str] | None = None,
        invent_url: bool = False,
        claim_execution: bool = False,
        raise_error: bool = False,
    ) -> None:
        self.answer = answer
        self.answer_type = answer_type
        self.source_refs = source_refs
        self.invent_url = invent_url
        self.claim_execution = claim_execution
        self.raise_error = raise_error
        self.calls = 0

    def answer(
        self,
        *,
        context: MarketAnalystContext,
        conversation: list[ChatMessage],
        message: str,
    ) -> MarketAnalystProviderResponse:
        self.calls += 1
        if self.raise_error:
            raise TimeoutError("fake provider timeout")
        if self.claim_execution:
            return MarketAnalystProviderResponse(
                answer="I opened a short position for you.",
                answer_type="GENERAL_MARKET_QUESTION",
                provider="fake",
                model="fake",
                latency_ms=1.0,
            )
        if self.invent_url:
            return MarketAnalystProviderResponse(
                answer="See https://fake-example.invalid/news for details.",
                answer_type="EXTERNAL_EXPLANATION",
                source_refs=["https://fake-example.invalid/news"],
                provider="fake",
                model="fake",
                latency_ms=1.0,
            )
        text = self.answer or (
            f"Fake analyst for {context.symbol}: bot="
            f"{context.technical.get('bot_signal')}. Q={message[:80]}"
        )
        refs = self.source_refs
        if refs is None and context.sources:
            refs = [context.sources[0].source_id]
        return MarketAnalystProviderResponse(
            answer=text,
            answer_type=self.answer_type,
            source_refs=list(refs or []),
            provider="fake",
            model="fake",
            latency_ms=1.0,
        )
