# PHASE 17.2.5D — Bright Modern Visual Redesign (Final Direction)

**Date:** 2026-09-09  
**Direction:** White canvas + modern rounded cards + Financial Blue interaction  
**Reference:** Approved mock (modern fintech / CMC clarity / workstation semantics)

## BEFORE → AFTER

| BEFORE | AFTER |
|--------|--------|
| Pale gray page canvas | White / bright workspace |
| Flat almost-no-shadow surfaces | Soft `--shadow-card` on concept cards |
| Near-black accent | Brand blue `#2563EB` for interaction only |
| Navy M15 block tied to accent | Semantic M15 (negative/positive-subtle) + diverging score bar |
| Form-like setup rows | Value blocks; TP1 execution target emphasized |
| Weak DEMO control | Accent primary segment (account profile, not execution) |
| Report-like single column | Analysis \| Setup \| Risk grid + Positions \| Chart |

## Tokens changed

`dashboard/app/globals.css`

- `--background: #FFFFFF`
- Surfaces, accent family, positive/negative/warning + `*-subtle`
- `--surface-active: var(--accent-subtle)`
- Radius: control/button/tab/card
- Shadows: xs / sm / card / card-hover
- Legacy aliases `@deprecated`

## Components changed

- Shell / Sidebar / Header / AccountSwitcher / BotStatusIndicator
- button, badge, card
- AccountOverviewSection, RealizedPnlChart
- SymbolTabs (card wrapper, scrollIntoView, accent underline)
- TradeDecisionHero, MtfScoreBar, TradeSetupCard, PriceRelationshipBar
- RiskAssessmentCard, DecisionReasonsCard, MultiTimeframeDetails
- TradeAnalysisSection (xl 6+3+3 grid)
- PositionTable + overview page (positions + chart grid)
- Symbol pair labels in `lib/symbols/config.ts`
- i18n: product tagline, nav groups, TP labels VI

## Screens reviewed

- Desktop ~1440: account card, blue DEMO, active nav rail, symbol tabs with SHORT + moves
- Desktop ~1920: brighter cards, soft depth, PnL hierarchy
- Analysis: SELL/SHORT tint, MTF score, setup TP1 target, risk statuses independent, BLOCKED `negative-subtle`
- Mobile width: sidebar `display:none` below `md`; stack preserved

## Explicit non-changes

- Sparkline: **omitted** (no historical series in UI data layer)
- Chart header **$ sum only** — no invented %
- Backend / strategy / ExecutionCandidate / broker mutation: **NONE / NO**

## Visual acceptance

- Bright / modern / card grouping: YES
- Brand blue without dominating semantics: YES
- Active symbol + price + SELL/SHORT scannable: YES
- M15 not brand-blue: YES (semantic tint + diverging bar)
- Buttons clickable; statuses not buttons: YES
- Residual: shadow still subtle by design; further density polish on secondary pages (Risk/Backtest) optional next pass
