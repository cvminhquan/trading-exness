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
    r"order_send"
    r")\b"
)

_URL_RE = re.compile(r"https?://[^\s\)\]\"']+", re.IGNORECASE)
_WIN_PROB = re.compile(
    r"(?i)\b(\d{1,3})\s*%\s*(win|thắng|probability|confidence)\b"
)


class ValidationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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
    if "[source omitted]" in sanitized and sanitized != answer:
        # invented URL present
        if any(
            u not in allowed_urls for u in _URL_RE.findall(answer)
        ):
            raise ValidationError("invented_url")

    sources = [allowed[r] for r in cleaned_refs if r in allowed]
    warnings = list(response.warnings or [])
    return sanitized, answer_type, cleaned_refs, sources, warnings
