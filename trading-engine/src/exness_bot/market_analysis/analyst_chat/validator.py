"""Validate and sanitize Market Analyst provider output."""

from __future__ import annotations

import re

from exness_bot.market_analysis.analyst_chat.models import (
    AnswerType,
    MarketAnalystContext,
    SourceRef,
)
from exness_bot.market_analysis.analyst_chat.provider_base import (
    MarketAnalystProviderResponse,
)

_ALLOWED_TYPES = {a.value for a in AnswerType}

_EXEC_CLAIM = re.compile(
    r"(?i)\b("
    r"i (opened|placed|executed|closed|bought|sold)|"
    r"position opened|"
    r"order (sent|placed|executed)|"
    r"buy now|sell now|"
    r"open 2 lots|"
    r"execute order|"
    r"đã (mở|đặt|khớp) lệnh|"
    r"order[\s_]*send"
    r")\b"
)

_URL_RE = re.compile(r"https?://[^\s\)\]\"']+", re.IGNORECASE)
_WIN_PROB = re.compile(
    r"(?i)\b(\d{1,3})\s*%\s*(win|thắng|probability|confidence)\b"
)

# External context must not be presented as the cause of mtf_technical_v1 signal.
_FALSE_EXTERNAL_CAUSALITY = re.compile(
    r"(?i)("
    r"bot\s+(đang\s+)?(wait|long|short).{0,60}(v[iì]|because|do).{0,40}external"
    r"|external.{0,40}(nên|makes?|causes?|khiến).{0,40}bot\s+(wait|long|short)"
    r"|bot\s+wait\s+v[iì]\s+(tin|external|macro)"
    r")"
)


class ValidationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _check_technical_contradiction(
    answer: str, context: MarketAnalystContext
) -> None:
    """Lightweight guard for critical structured facts (not full NLP)."""
    lower = answer.lower()
    tech = context.technical or {}
    signal = str(tech.get("bot_signal") or "").upper()
    tfs = tech.get("timeframes") or {}
    m15 = (tfs.get("M15") or {}) if isinstance(tfs, dict) else {}
    m15_trend = str(m15.get("trend") or "").upper()

    if (
        signal == "WAIT"
        and re.search(r"(?i)bot\s+(đang\s+)?(long|short)\b", answer)
        and "wait" not in lower
    ):
        raise ValidationError("technical_contradiction_bot_signal")
    if m15_trend == "BULLISH" and re.search(
        r"(?i)m15\s+(đang\s+)?bearish", answer
    ):
        raise ValidationError("technical_contradiction_m15")
    if m15_trend == "BEARISH" and re.search(
        r"(?i)m15\s+(đang\s+)?bullish", answer
    ):
        raise ValidationError("technical_contradiction_m15")


def validate_provider_response(
    response: MarketAnalystProviderResponse,
    *,
    context: MarketAnalystContext,
    max_answer_length: int = 6000,
) -> tuple[str, str, list[str], list[SourceRef], list[str]]:
    answer = (response.answer or "").strip()
    if not answer:
        raise ValidationError("empty_answer")
    if len(answer) > max_answer_length:
        answer = answer[:max_answer_length].rstrip() + "…"
    if _EXEC_CLAIM.search(answer):
        raise ValidationError("execution_language")
    if _WIN_PROB.search(answer):
        raise ValidationError("fabricated_probability")
    if _FALSE_EXTERNAL_CAUSALITY.search(answer):
        raise ValidationError("false_external_causality")
    _check_technical_contradiction(answer, context)

    answer_type = (response.answer_type or "").strip().upper()
    if answer_type not in _ALLOWED_TYPES:
        answer_type = AnswerType.GENERAL_MARKET_QUESTION.value

    allowed = {s.source_id: s for s in context.sources}
    allowed_urls = {s.url for s in context.sources}
    cleaned_refs: list[str] = []
    for ref in response.source_refs:
        rid = str(ref).strip()
        if rid in allowed:
            cleaned_refs.append(rid)
        elif rid.startswith("http"):
            # invented URL as ref — reject
            continue
    # Strip invented URLs from answer body
    def _keep_url(match: re.Match[str]) -> str:
        url = match.group(0)
        return url if url in allowed_urls else "[source omitted]"

    sanitized = _URL_RE.sub(_keep_url, answer)
    if (
        "[source omitted]" in sanitized
        and sanitized != answer
        and any(u not in allowed_urls for u in _URL_RE.findall(answer))
    ):
        raise ValidationError("invented_url")

    sources = [allowed[r] for r in cleaned_refs if r in allowed]
    warnings = list(response.warnings or [])
    return sanitized, answer_type, cleaned_refs, sources, warnings
