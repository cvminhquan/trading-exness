"""Report helpers + human markdown for Phase 16.2.4A.2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.research.forward.protocol import (
    OBSERVED_DATA_CUTOFF_UTC,
    PROTOCOL_VERSION,
)
from exness_bot.market_analysis.research.forward.store import (
    default_forward_root,
    report_path,
    state_path,
)


def load_state(root: Path | None = None) -> dict[str, Any]:
    path = state_path(root=root)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return dict(raw) if isinstance(raw, dict) else {}


def load_report(root: Path | None = None) -> dict[str, Any]:
    path = report_path(root=root)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return dict(raw) if isinstance(raw, dict) else {}


def status_summary(root: Path | None = None) -> dict[str, Any]:
    state = load_state(root)
    report = load_report(root)
    return {
        "protocol_version": state.get("protocol_version", PROTOCOL_VERSION),
        "observed_cutoff": OBSERVED_DATA_CUTOFF_UTC.isoformat(),
        "forward_rows": state.get("forward_rows", 0),
        "forward_first_timestamp": state.get("forward_first_timestamp"),
        "forward_last_timestamp": state.get("forward_last_timestamp"),
        "evidence_status": state.get("evidence_status", "INSUFFICIENT_FORWARD_DATA"),
        "contaminated": state.get("contaminated", False),
        "precommitted_signal_count": state.get("precommitted_signal_count", 0),
        "retrospective_signal_count": state.get("retrospective_signal_count", 0),
        "pending_outcomes": state.get("pending_outcomes", 0),
        "matured_trades_v1": state.get("matured_trades_v1", 0),
        "matured_trades_v2": state.get("matured_trades_v2", 0),
        "research_verdict": state.get("research_verdict", "PROMISING_V2_REQUIRES_MORE_DATA"),
        "promotion": state.get("promotion", "NO"),
        "quality_status": state.get("quality_status")
        or (report.get("quality") or {}).get("quality_status"),
        "paths": {
            "root": str(root or default_forward_root()),
            "state": str(state_path(root=root)),
            "report": str(report_path(root=root)),
        },
    }


def render_human_report_md(report: dict[str, Any], state: dict[str, Any]) -> str:
    """Fill docs template sections — use PENDING/INSUFFICIENT when empty."""
    evidence = state.get("evidence_status", "INSUFFICIENT_FORWARD_DATA")
    q = report.get("quality") or {}
    ds = report.get("dataset") or {}
    v1 = report.get("v1_metrics") or {}
    v2 = report.get("v2_metrics") or {}
    cont = report.get("contamination") or {}

    def _metric_block(label: str, m: dict[str, Any]) -> str:
        if not m or m.get("trade_count", 0) == 0:
            return f"### {label}\n\nINSUFFICIENT_FORWARD_DATA / PENDING\n"
        return (
            f"### {label}\n\n"
            f"- trade_count: {m.get('trade_count')}\n"
            f"- win_rate: {m.get('win_rate')}\n"
            f"- profit_factor: {m.get('profit_factor')}\n"
            f"- expectancy_R: {m.get('expectancy_R')}\n"
            f"- max_drawdown_R: {m.get('max_drawdown_R')}\n"
        )

    return f"""# M15-First Forward Validation

## 1. Purpose

Khóa protocol forward unseen cho `mtf_technical_v1` vs frozen `mtf_technical_v2_candidate`.
Phase này **không** tối ưu chiến lược. PASS = harness đúng, không phải V2 đã validate.

## 2. Observed Cutoff

- OBSERVED_DATA_CUTOFF_UTC: `{OBSERVED_DATA_CUTOFF_UTC.isoformat()}`
- Mọi candle `timestamp <= cutoff` → OBSERVED (không bao giờ unseen)
- Protocol version: `{PROTOCOL_VERSION}`

## 3. Frozen Strategies

- V1: `mtf_technical_v1` (không sửa)
- V2: `mtf_technical_v2_candidate` — freeze 16.2.4 (assert fail-closed)
- Metric fingerprint: `{state.get("metric_definition_hash", "PENDING")}`
- V2 freeze hash: `{state.get("v2_freeze_hash", "PENDING")}`

## 4. Pre-Registered Hypotheses

- **H1** ASYMMETRIC_LEAD_QUALITY — MEASURE_ONLY
- **H2** SAME_DIRECTION_CLUSTERING (gap ≤ 8) — MEASURE_ONLY; no cooldown
- **H3** LATENCY_ADVANTAGE (buckets 1-2 / 3-4 / 5-8 / 9+ / never) — MEASURE_ONLY

## 5. Data Collection

- Store: `data/forward/{{symbol}}_M15_forward.csv`
- Collector: manual/idempotent read-only MT5 (`copy_rates*`)
- PRECOMMITTED: schema/journal only — **chưa** wire CandleEngine
- Init evaluation mode: `RETROSPECTIVE_REPLAY`

## 6. Provenance

- Forward rows: `{ds.get("forward_rows", 0)}`
- First / last: `{ds.get("first_timestamp")}` / `{ds.get("last_timestamp")}`
- Dataset hash: `{ds.get("dataset_hash")}`
- Provenance: xem `*_forward_provenance.json`

## 7. No-Look-Ahead

Reuse Phase 16.2.4A: prefix window `m15[:i+1]`, HTF closed buckets only.
Warmup = OBSERVED bars trước cutoff (không vào forward metrics).

## 8. Outcome Assumptions

Exact 16.2.4A: entry=close[t], SL=1.5*ATR, TP=2R, horizon=96, SL-first same bar, whipsaw<=4.

## 9. Evidence Gates

- ≥ 2000 CLOSED M15 mới **và** ≥ 30 calendar days **và** đủ matured trades
- Stronger target: ≥ 3000 M15 + nhiều regime
- Current: **{evidence}**

## 10. V1 Metrics

{_metric_block("V1", v1)}

## 11. V2 Metrics

{_metric_block("V2", v2)}

## 12. Lead Cohorts

Pre-registered only. Chi tiết machine-readable: `m15_forward_validation_report.json` → `cohorts`.

Status: {"PENDING" if evidence != "FORWARD_WINDOW_COMPLETE" else "SEE_JSON"}

## 13. LONG vs SHORT

Report độc lập V1/V2 LONG/SHORT — không disable LONG.
Status: {"PENDING" if (v2.get("trade_count") or 0) == 0 else "SEE_JSON"}

## 14. Signal Clustering

Định nghĩa khóa: SIGNAL_CLUSTER gap 1…8 M15 bars. No cooldown.
Status: {"PENDING" if (v2.get("trade_count") or 0) == 0 else "SEE_JSON"}

## 15. Latency Buckets

Buckets khóa: 1-2, 3-4, 5-8, 9+, v1_never_directional.
Status: PENDING / SEE_JSON

## 16. Regimes

Canonical regimes only (không invent category theo outcome).
Status: PENDING / SEE_JSON

## 17. Data Quality

- quality_status: **{q.get("quality_status", "PASS")}**
- row_count: {q.get("row_count", 0)}
- duplicate_count: {q.get("duplicate_count", 0)}
- unexpected_active_session_gaps: {q.get("unexpected_active_session_gaps", 0)}

## 18. Contamination Status

- contaminated: **{cont.get("contaminated", False)}**
- reason: {cont.get("reason")}
- Nếu tune sau khi xem forward → `CONTAMINATED_BY_TUNING` + cutoff/window mới

## 19. Current Evidence Status

**{evidence}**

Research verdict: `PROMISING_V2_REQUIRES_MORE_DATA`  
Promotion: **NO**

## 20. Next Evaluation

1. `python -m exness_bot.market_analysis.research.forward collect --symbol XAUUSD`
2. `python -m exness_bot.market_analysis.research.forward evaluate --symbol XAUUSD`
3. `python -m exness_bot.market_analysis.research.forward report --symbol XAUUSD`
4. Không bắt đầu 16.2.4B / retune / promote cho đến khi human review + đủ evidence gate.
"""


def write_human_report(
    docs_path: Path,
    *,
    root: Path | None = None,
) -> Path:
    report = load_report(root)
    state = load_state(root)
    text = render_human_report_md(report, state)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(text, encoding="utf-8")
    return docs_path
