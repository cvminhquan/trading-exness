"""Lightweight deterministic intent routing for analyst chat."""

from __future__ import annotations

import re

from exness_bot.market_analysis.analyst_chat.models import ChatIntent

_EXEC_PATTERNS = (
    r"\bmở lệnh\b",
    r"\bđặt lệnh\b",
    r"\bexecute\b",
    r"\border_send\b",
    r"\bbuy now\b",
    r"\bsell now\b",
    r"\bopen (a )?(long|short|position)\b",
    r"\bclose (my )?position\b",
    r"\bincrease (lot|size|volume)\b",
    r"\btăng lot\b",
    r"\bapprove (the )?trade\b",
)

_WHY_BOT = (
    r"tại sao bot",
    r"why (is )?the bot",
    r"bot đang",
    r"bot (wait|long|short)",
    r"why.*(wait|long|short)",
)

_PRICE = (r"giá hiện tại", r"current price", r"giá bao nhiêu", r"price now")

_TF_CONFLICT = (
    r"h4.*m15",
    r"m15.*h4",
    r"timeframe conflict",
    r"xung đột.*khung",
    r"cùng hướng",
    r"confirm",
)

_SR = (r"support", r"resistance", r"hỗ trợ", r"kháng cự", r"\bs/r\b")

_EXTERNAL = (
    r"external",
    r"macro",
    r"usd",
    r"treasury",
    r"ngoại",
    r"support hay conflict",
    r"conflict",
)

_EVENT = (r"event risk", r"sự kiện", r"nfp", r"fomc", r"cpi")

_WATCH = (r"theo dõi", r"what to watch", r"cần chú ý", r"watch next")

_TECH = (
    r"technical",
    r"m15",
    r"h1",
    r"rsi",
    r"ema",
    r"atr",
    r"cấu trúc",
    r"structure",
    r"trend",
)


def classify_intent(message: str) -> ChatIntent:
    text = (message or "").strip().lower()
    if not text:
        return ChatIntent.GENERAL
    for pat in _EXEC_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return ChatIntent.EXECUTION_REQUEST
    for group, intent in (
        (_WHY_BOT, ChatIntent.WHY_BOT_SIGNAL),
        (_PRICE, ChatIntent.CURRENT_PRICE),
        (_EVENT, ChatIntent.EVENT_RISK),
        (_WATCH, ChatIntent.WHAT_TO_WATCH),
        (_SR, ChatIntent.SUPPORT_RESISTANCE),
        (_TF_CONFLICT, ChatIntent.TIMEFRAME_CONFLICT),
        (_EXTERNAL, ChatIntent.EXTERNAL_CONTEXT),
        (_TECH, ChatIntent.TECHNICAL_STATE),
    ):
        for pat in group:
            if re.search(pat, text, flags=re.IGNORECASE):
                return intent
    return ChatIntent.GENERAL
