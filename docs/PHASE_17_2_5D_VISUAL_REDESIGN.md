# PHASE 17.2.5D — Bright Modern Visual Redesign (Final Direction)

**Date:** 2026-09-09  
**Status:** PASS — see full report `docs/PHASE_17_2_5D_REPORT.md`  
**Direction:** White / cool-gray canvas + modern rounded cards + Financial Blue interaction  
**Reference:** Approved mock (modern fintech / CMC clarity / workstation semantics)

## BEFORE → AFTER

| BEFORE | AFTER |
|--------|--------|
| Pale gray page canvas | Cool page `#F4F7FB` + white cards |
| Flat almost-no-shadow surfaces | Soft `--shadow-card` on concept cards |
| Near-black accent | Brand blue `#2563EB` for interaction only |
| Navy M15 block tied to accent | Semantic M15 (negative/positive-subtle) + diverging score bar |
| Form-like setup rows | Value blocks; TP1 execution target emphasized |
| Segment DEMO/LIVE | Pill `DEMO ▾` / `LIVE ▾` + loading overlay |
| Symbol mini-cards rời | Full-width strip; L-active; sparkline; Thêm symbol |
| Realized PnL fixed 7d | Filter 7 / 30 days |

## Tokens changed

`dashboard/app/globals.css`

- Page `--background: #F4F7FB`; surfaces; accent family; positive/negative/warning + `*-subtle`
- `--surface-active: var(--accent-subtle)`
- Radius + shadows; legacy aliases `@deprecated`

## Components changed

- Shell / Sidebar / Header / AccountSwitcher (pill + blocking load)
- SymbolTabs / MiniSparkline / session-sparkline / session moves
- TradeDecisionHero, TradeSetupCard, PriceRelationshipBar, Risk, Reasons
- TradeAnalysisSection (3-col overview; MTF details on Trades only)
- RealizedPnlChart (7/30)
- i18n VI + `isValidMarketSymbol`

## Explicit non-changes

- Sparkline = session mid samples only (not fabricated 24h candles)
- Chart header **$ sum only** — no invented %
- Backend strategy / ExecutionCandidate / broker mutation: **NONE**

## Verdict

```text
PHASE 17.2.5D: PASS (UI-only)
Full write-up: docs/PHASE_17_2_5D_REPORT.md
```
