"""Deterministic fake AI provider for offline tests."""

from __future__ import annotations

from exness_bot.market_analysis.synthesis.models import MarketSynthesisNarrative
from exness_bot.market_analysis.synthesis.provider_base import (
    MarketSynthesisPromptInput,
    MarketSynthesisProviderResult,
)


class FakeMarketSynthesisProvider:
    name = "fake"

    def __init__(
        self,
        *,
        scenario: str = "ok",
        model: str = "fake-synthesis",
    ) -> None:
        self.scenario = scenario
        self.model = model

    def generate_explanation(
        self, request: MarketSynthesisPromptInput
    ) -> MarketSynthesisProviderResult:
        if self.scenario == "timeout":
            return MarketSynthesisProviderResult(
                ok=False,
                narrative=None,
                latency_ms=30_000.0,
                error_type="timeout",
                provider=self.name,
                model=self.model,
            )
        if self.scenario == "execution_language":
            return MarketSynthesisProviderResult(
                ok=True,
                narrative=MarketSynthesisNarrative(
                    summary="SELL NOW and open 2 lots.",
                    technical_explanation="Execute order immediately.",
                    external_explanation="Buy now.",
                    alignment_explanation="Set stop loss here.",
                    risk_explanation="90% probability.",
                    uncertainties=[],
                    what_to_watch=["Enter long now"],
                ),
                latency_ms=12.0,
                provider=self.name,
                model=self.model,
            )
        if self.scenario == "mutate_technical":
            # Attempts to claim opposite technical — validator still OK textually,
            # but service must keep structured views unchanged.
            tech = (request.payload.get("technical") or {}).get("primary_bias")
            return MarketSynthesisProviderResult(
                ok=True,
                narrative=MarketSynthesisNarrative(
                    summary=f"AI claims M15 is bullish (input was {tech}).",
                    technical_explanation="M15 is bullish.",
                    external_explanation="External bias is bearish.",
                    alignment_explanation="Aligned per AI.",
                    risk_explanation="Event risk unknown.",
                    uncertainties=["AI may disagree with facts"],
                    what_to_watch=["Watch structure"],
                ),
                latency_ms=15.0,
                provider=self.name,
                model=self.model,
            )
        if self.scenario == "invented_url":
            return MarketSynthesisProviderResult(
                ok=True,
                narrative=MarketSynthesisNarrative(
                    summary="See https://evil.example/fake for proof.",
                    technical_explanation="Technical ok.",
                    external_explanation="External ok.",
                    alignment_explanation="Mixed.",
                    risk_explanation="Low.",
                    uncertainties=[],
                    what_to_watch=["Watch price"],
                ),
                latency_ms=10.0,
                provider=self.name,
                model=self.model,
            )

        tech = request.payload.get("technical") or {}
        ext = request.payload.get("external") or {}
        state = request.payload.get("deterministic_state")
        return MarketSynthesisProviderResult(
            ok=True,
            narrative=MarketSynthesisNarrative(
                summary=(
                    f"{request.symbol}: AI summary for state {state}. "
                    f"M15 {tech.get('primary_bias')}; external {ext.get('external_bias')}."
                ),
                technical_explanation=(
                    f"Technical view shows M15 {tech.get('primary_bias')} with "
                    f"bot signal {tech.get('bot_signal')}."
                ),
                external_explanation=(
                    f"External bias {ext.get('external_bias')} with "
                    f"event risk {ext.get('event_risk')}."
                ),
                alignment_explanation=(
                    f"Alignment is {ext.get('alignment_with_technical')}."
                ),
                risk_explanation=f"Event risk is {ext.get('event_risk')}.",
                uncertainties=["Model explanation is approximate"],
                what_to_watch=["Watch M15 structure and flagged events"],
            ),
            latency_ms=18.0,
            provider=self.name,
            model=self.model,
        )
