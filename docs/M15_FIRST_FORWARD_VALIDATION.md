# M15-First Forward Validation

## 1. Purpose

Khóa protocol forward unseen cho `mtf_technical_v1` vs frozen `mtf_technical_v2_candidate`.
Phase này **không** tối ưu chiến lược. PASS = harness đúng, không phải V2 đã validate.

## 2. Observed Cutoff

- OBSERVED_DATA_CUTOFF_UTC: `2026-09-08T16:00:00+00:00`
- Mọi candle `timestamp <= cutoff` → OBSERVED (không bao giờ unseen)
- Protocol version: `16.2.4A.2`

## 3. Frozen Strategies

- V1: `mtf_technical_v1` (không sửa)
- V2: `mtf_technical_v2_candidate` — freeze 16.2.4 (assert fail-closed)
- Metric fingerprint: `beebf45202021823`
- V2 freeze hash: `aca4917e94c1ac08`

## 4. Pre-Registered Hypotheses

- **H1** ASYMMETRIC_LEAD_QUALITY — MEASURE_ONLY
- **H2** SAME_DIRECTION_CLUSTERING (gap ≤ 8) — MEASURE_ONLY; no cooldown
- **H3** LATENCY_ADVANTAGE (buckets 1-2 / 3-4 / 5-8 / 9+ / never) — MEASURE_ONLY

## 5. Data Collection

- Store: `data/forward/{symbol}_M15_forward.csv`
- Collector: manual/idempotent read-only MT5 (`copy_rates*`)
- PRECOMMITTED: schema/journal only — **chưa** wire CandleEngine
- Init evaluation mode: `RETROSPECTIVE_REPLAY`

## 6. Provenance

- Forward rows: `20`
- First / last: `2026-09-08T16:15:00+00:00` / `2026-09-08T22:00:00+00:00`
- Dataset hash: `057cec652646ac84761cf2e2df6f3fad`
- Provenance: xem `*_forward_provenance.json`

## 7. No-Look-Ahead

Reuse Phase 16.2.4A: prefix window `m15[:i+1]`, HTF closed buckets only.
Warmup = OBSERVED bars trước cutoff (không vào forward metrics).

## 8. Outcome Assumptions

Exact 16.2.4A: entry=close[t], SL=1.5*ATR, TP=2R, horizon=96, SL-first same bar, whipsaw<=4.

## 9. Evidence Gates

- ≥ 2000 CLOSED M15 mới **và** ≥ 30 calendar days **và** đủ matured trades
- Stronger target: ≥ 3000 M15 + nhiều regime
- Current: **INSUFFICIENT_FORWARD_DATA**

## 10. V1 Metrics

### V1

INSUFFICIENT_FORWARD_DATA / PENDING


## 11. V2 Metrics

### V2

INSUFFICIENT_FORWARD_DATA / PENDING


## 12. Lead Cohorts

Pre-registered only. Chi tiết machine-readable: `m15_forward_validation_report.json` → `cohorts`.

Status: PENDING

## 13. LONG vs SHORT

Report độc lập V1/V2 LONG/SHORT — không disable LONG.
Status: PENDING

## 14. Signal Clustering

Định nghĩa khóa: SIGNAL_CLUSTER gap 1…8 M15 bars. No cooldown.
Status: PENDING

## 15. Latency Buckets

Buckets khóa: 1-2, 3-4, 5-8, 9+, v1_never_directional.
Status: PENDING / SEE_JSON

## 16. Regimes

Canonical regimes only (không invent category theo outcome).
Status: PENDING / SEE_JSON

## 17. Data Quality

- quality_status: **PASS**
- row_count: 20
- duplicate_count: 0
- unexpected_active_session_gaps: 0

## 18. Contamination Status

- contaminated: **False**
- reason: None
- Nếu tune sau khi xem forward → `CONTAMINATED_BY_TUNING` + cutoff/window mới

## 19. Current Evidence Status

**INSUFFICIENT_FORWARD_DATA**

Research verdict: `PROMISING_V2_REQUIRES_MORE_DATA`  
Promotion: **NO**

## 20. Next Evaluation

1. `python -m exness_bot.market_analysis.research.forward collect --symbol XAUUSD`
2. `python -m exness_bot.market_analysis.research.forward evaluate --symbol XAUUSD`
3. `python -m exness_bot.market_analysis.research.forward report --symbol XAUUSD`
4. Không bắt đầu 16.2.4B / retune / promote cho đến khi human review + đủ evidence gate.
