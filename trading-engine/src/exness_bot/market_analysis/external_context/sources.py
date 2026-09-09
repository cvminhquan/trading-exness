"""Source URL safety, classification, and deduplication."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from exness_bot.market_analysis.external_context.models import SourceType

_OFFICIAL_DOMAINS = frozenset(
    {
        "federalreserve.gov",
        "treasury.gov",
        "bls.gov",
        "bea.gov",
        "census.gov",
        "imf.org",
        "bis.org",
        "ecb.europa.eu",
        "boj.or.jp",
        "bankofengland.co.uk",
    }
)
_MAJOR_NEWS = frozenset(
    {
        "reuters.com",
        "bloomberg.com",
        "wsj.com",
        "ft.com",
        "apnews.com",
        "bbc.com",
        "bbc.co.uk",
        "nytimes.com",
    }
)
_FINANCIAL_NEWS = frozenset(
    {
        "cnbc.com",
        "marketwatch.com",
        "investing.com",
        "kitco.com",
        "forexlive.com",
        "fxstreet.com",
        "yahoo.com",
        "finance.yahoo.com",
    }
)


def normalize_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"https", "http"}:
        return None
    if not parsed.netloc:
        return None
    # Drop fragments and common tracking params
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
        query=urlencode(query),
    )
    return urlunparse(cleaned)


def domain_of(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def classify_source_type(domain: str) -> SourceType:
    d = domain.lower()
    if d in _OFFICIAL_DOMAINS or any(d.endswith("." + x) for x in _OFFICIAL_DOMAINS):
        return SourceType.OFFICIAL
    if d in _MAJOR_NEWS or any(d.endswith("." + x) for x in _MAJOR_NEWS):
        return SourceType.MAJOR_NEWS
    if d in _FINANCIAL_NEWS or any(d.endswith("." + x) for x in _FINANCIAL_NEWS):
        return SourceType.FINANCIAL_NEWS
    if "gov" in d.split("."):
        return SourceType.OFFICIAL
    return SourceType.UNKNOWN


def dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        n = normalize_url(u)
        if n is None or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out
