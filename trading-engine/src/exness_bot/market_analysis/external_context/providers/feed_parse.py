"""Shared RSS/Atom XML parsing — titles/links/dates only (no article bodies)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from exness_bot.market_analysis.external_context.sources import normalize_url

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class FeedEntry:
    title: str
    link: str
    published_at: str | None
    category: str | None = None


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def parse_rfc822_or_iso(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except ValueError:
        return None


def _rss_link(item: ET.Element) -> str | None:
    link_el = None
    for child in item:
        if _local(child.tag) == "link":
            link_el = child
            break
    href = _text(link_el)
    if href:
        return normalize_url(href)
    # Some feeds put link in guid
    for child in item:
        if _local(child.tag) == "guid":
            g = _text(child)
            if g.startswith("http"):
                return normalize_url(g)
    return None


def _atom_link(entry: ET.Element) -> str | None:
    for child in entry:
        if _local(child.tag) != "link":
            continue
        href = child.attrib.get("href") or ""
        rel = (child.attrib.get("rel") or "alternate").lower()
        if rel in {"alternate", ""} and href:
            return normalize_url(href)
    return None


def parse_feed_xml(
    raw: bytes | str,
    *,
    default_category: str | None = None,
    max_entries: int = 40,
) -> list[FeedEntry]:
    """Parse RSS 2.0 or Atom. Raises ValueError on malformed XML."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    # Strip BOM / leading junk before root
    text = text.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("empty_feed")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("malformed_xml") from exc

    root_local = _local(root.tag).lower()
    entries: list[FeedEntry] = []

    if root_local == "rss" or root_local == "rdf":
        channel = None
        for child in root:
            if _local(child.tag).lower() == "channel":
                channel = child
                break
        items_parent = channel if channel is not None else root
        for item in items_parent:
            if _local(item.tag).lower() != "item":
                continue
            title = ""
            pub_raw = None
            cat = default_category
            for child in item:
                loc = _local(child.tag).lower()
                if loc == "title":
                    title = _text(child)
                elif loc in {"pubdate", "date", "published"}:
                    pub_raw = _text(child)
                elif loc == "category" and cat is None:
                    cat = _text(child) or None
            link = _rss_link(item)
            if not title or not link:
                continue
            entries.append(
                FeedEntry(
                    title=title[:400],
                    link=link,
                    published_at=parse_rfc822_or_iso(pub_raw),
                    category=cat,
                )
            )
            if len(entries) >= max_entries:
                break
        return entries

    # Atom
    atom_entries = list(root.findall("atom:entry", _ATOM_NS))
    if not atom_entries:
        atom_entries = [e for e in root if _local(e.tag).lower() == "entry"]
    for entry in atom_entries:
        title = ""
        pub_raw = None
        for child in entry:
            loc = _local(child.tag).lower()
            if loc == "title":
                title = _text(child)
            elif loc in {"updated", "published"} and (
                pub_raw is None or loc == "published"
            ):
                pub_raw = _text(child)
        link = _atom_link(entry)
        if not title or not link:
            continue
        entries.append(
            FeedEntry(
                title=title[:400],
                link=link,
                published_at=parse_rfc822_or_iso(pub_raw),
                category=default_category,
            )
        )
        if len(entries) >= max_entries:
            break
    return entries


def dedupe_feed_entries(entries: list[FeedEntry]) -> list[FeedEntry]:
    seen: set[str] = set()
    out: list[FeedEntry] = []
    for e in entries:
        key = e.link.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


_HAWKISH = re.compile(
    r"\b(hike|hiking|tighten|tightening|restrictive|higher\s+rates|"
    r"elevated\s+for\s+longer|hawkish)\b",
    re.I,
)
_DOVISH = re.compile(
    r"\b(cut|cutting|ease|easing|accommodative|dovish|lower\s+rates|"
    r"rate\s+cut)\b",
    re.I,
)


def classify_fed_tone(title: str) -> str:
    """Heuristic title tone — not a trade signal."""
    if _HAWKISH.search(title) and not _DOVISH.search(title):
        return "HAWKISH"
    if _DOVISH.search(title) and not _HAWKISH.search(title):
        return "DOVISH"
    return "NEUTRAL"
