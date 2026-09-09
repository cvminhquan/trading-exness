"""Deterministic fallback answers from MarketAnalystContext."""

from __future__ import annotations

from exness_bot.market_analysis.analyst_chat.models import (
    AnswerType,
    ChatIntent,
    MarketAnalystContext,
)


def _tf_line(ctx: MarketAnalystContext, tf: str) -> str:
    block = (ctx.technical.get("timeframes") or {}).get(tf) or {}
    role = block.get("role") or tf
    trend = block.get("trend") or "UNKNOWN"
    structure = block.get("structure") or "UNKNOWN"
    return f"{tf} ({role}): trend={trend}, structure={structure}"


def build_fallback_answer(
    *,
    intent: ChatIntent,
    context: MarketAnalystContext,
) -> tuple[str, AnswerType, list[str]]:
    tech = context.technical
    ext = context.external
    syn = context.synthesis
    signal = tech.get("bot_signal") or "UNKNOWN"
    strategy = tech.get("bot_strategy") or "mtf_technical_v1"
    warnings: list[str] = []
    source_refs: list[str] = []

    if intent is ChatIntent.EXECUTION_REQUEST:
        return (
            "Chat Analyst chỉ phân tích và giải thích — không thể gửi lệnh, "
            "mở/đóng vị thế, chỉnh SL/TP hay thay đổi volume. "
            f"Trạng thái technical hiện tại: bot signal={signal} "
            f"(strategy={strategy}).",
            AnswerType.READ_ONLY_REFUSAL,
            [],
        )

    if intent is ChatIntent.WHY_BOT_SIGNAL:
        parts = [
            f"Bot signal: {signal} (strategy {strategy}).",
            "Bot signal đến từ technical strategy; external context "
            "không tham gia tính signal hiện tại.",
            _tf_line(context, "M15"),
            _tf_line(context, "H1"),
            _tf_line(context, "H4"),
            f"MTF alignment: {tech.get('mtf_alignment') or 'N/A'}; "
            f"setup={tech.get('setup_state') or 'N/A'}; "
            f"execution_status={tech.get('execution_status') or 'N/A'}.",
        ]
        if syn.get("technical_explanation"):
            parts.append(str(syn["technical_explanation"])[:400])
        align = ext.get("alignment_with_technical")
        if align:
            parts.append(
                f"External alignment (tham khảo, không quyết định signal): {align}."
            )
        return ("\n".join(parts), AnswerType.BOT_SIGNAL_EXPLANATION, [])

    if intent is ChatIntent.CURRENT_PRICE:
        price = tech.get("current_price")
        fresh = context.freshness.get("technical")
        if price is None:
            return (
                "Giá hiện tại không khả dụng trong technical snapshot.",
                AnswerType.INSUFFICIENT_CONTEXT,
                [],
            )
        stale_note = ""
        if isinstance(fresh, dict) and fresh.get("status") == "STALE":
            stale_note = " (quote/snapshot có thể đã cũ)"
            warnings.append("technical_stale")
        return (
            f"Giá tham chiếu từ snapshot: {price}{stale_note}.",
            AnswerType.TECHNICAL_EXPLANATION,
            [],
        )

    if intent is ChatIntent.TIMEFRAME_CONFLICT:
        text = (
            "Vai trò khung thời gian: M15=PRIMARY, H1=CONFIRMATION, "
            "H4=CONTEXT, D1=MACRO_CONTEXT. "
            "Conflict giữa khung cao hơn và M15 không tự động override "
            "signal M15.\n"
            f"{_tf_line(context, 'M15')}\n"
            f"{_tf_line(context, 'H1')}\n"
            f"{_tf_line(context, 'H4')}\n"
            f"{_tf_line(context, 'D1')}"
        )
        return text, AnswerType.TECHNICAL_EXPLANATION, []

    if intent is ChatIntent.SUPPORT_RESISTANCE:
        m15 = (tech.get("timeframes") or {}).get("M15") or {}
        return (
            f"M15 nearest support={m15.get('nearest_support')}; "
            f"nearest resistance={m15.get('nearest_resistance')}.",
            AnswerType.TECHNICAL_EXPLANATION,
            [],
        )

    if intent is ChatIntent.EXTERNAL_CONTEXT:
        if str(ext.get("status") or "").upper() in {
            "DISABLED",
            "UNAVAILABLE",
            "",
        }:
            return (
                "External context hiện không khả dụng / chưa được bật.",
                AnswerType.INSUFFICIENT_CONTEXT,
                [],
            )
        refs = [s.source_id for s in context.sources[:5]]
        source_refs = refs
        text = (
            f"External bias={ext.get('external_bias')}; "
            f"evidence={ext.get('evidence_strength')}; "
            f"alignment_with_technical={ext.get('alignment_with_technical')}; "
            f"event_risk={ext.get('event_risk')}. "
            "External context không quyết định bot signal."
        )
        return text, AnswerType.EXTERNAL_EXPLANATION, source_refs

    if intent is ChatIntent.EVENT_RISK:
        events = ext.get("important_events") or []
        risk = ext.get("event_risk") or "UNKNOWN"
        if not events and str(ext.get("status") or "").upper() in {
            "DISABLED",
            "UNAVAILABLE",
            "",
        }:
            return (
                "Không có external event risk khả dụng.",
                AnswerType.INSUFFICIENT_CONTEXT,
                [],
            )
        lines = [f"Event risk: {risk}"]
        for e in events[:5]:
            if isinstance(e, dict):
                lines.append(
                    f"- {e.get('title') or e.get('event') or e}: "
                    f"{e.get('timing') or ''}"
                )
            else:
                lines.append(f"- {e}")
        return "\n".join(lines), AnswerType.RISK_EXPLANATION, []

    if intent is ChatIntent.WHAT_TO_WATCH:
        watch = syn.get("what_to_watch") or []
        if watch:
            return (
                "Cần theo dõi:\n" + "\n".join(f"- {w}" for w in watch[:6]),
                AnswerType.SYNTHESIS_EXPLANATION,
                [],
            )
        return (
            "Chưa có danh sách what_to_watch từ synthesis.",
            AnswerType.INSUFFICIENT_CONTEXT,
            [],
        )

    if intent is ChatIntent.TECHNICAL_STATE:
        return (
            f"Bot={signal}; alignment={tech.get('mtf_alignment')}.\n"
            f"{_tf_line(context, 'M15')}\n{_tf_line(context, 'H1')}",
            AnswerType.TECHNICAL_EXPLANATION,
            [],
        )

    # GENERAL
    summary = syn.get("summary") or ""
    if summary:
        return (
            f"AI Analyst deterministic fallback.\n{summary[:500]}",
            AnswerType.SYNTHESIS_EXPLANATION,
            [],
        )
    return (
        "AI Analyst hiện không khả dụng đầy đủ. "
        f"Dữ liệu hiện tại: bot={signal}, "
        f"context_status={context.context_status}.",
        AnswerType.GENERAL_MARKET_QUESTION,
        [],
    )
