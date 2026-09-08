# Dashboard TasteSkill Design Audit — 2026-09-08

Applied operator-focused design system (dense / calm / financial).

## What changed

| Area | Before | After |
|------|--------|--------|
| Tokens | large radius, soft slate cards | 4px radius, neutral gray, `tnum` |
| Card/Badge | shadow + rounded-xl + rainbow fills | thin border / outline state chips |
| Symbol tabs | dark pill tiles | underline workspace tabs + price |
| Decision | marketing hero + nested metrics | terminal scan: symbol·price·LIVE → signal·MTF → TF roles |
| Setup/Risk/Reasons | bordered cards | section separators |
| Overview order | account first | tabs → decision → positions → account/PnL tertiary |
| Positions | 4 metric boxes | inline summary strip |
| Strategy | card + indicator pills | separators + RESEARCH ONLY state badge |
| Tables | Card-wrapped | bare compact rows |

## Screenshot review

### Dashboard XAUUSD (`design-audit-xauusd.png`)
- **Primary focus:** CLEAR — `SELL / SHORT` + MTF −43.96 scans first
- **Density:** improved; still some vertical air under TF row (H4/D1 below fold OK)
- **Card count:** ~0 in analysis block (separators only)
- **Repeated info:** price appears in tab + decision (acceptable for workspace)
- **Spacing:** section gaps ~16px; good
- **Alignment:** TF labels left / scores right — OK
- **Typography:** decision 2xl; supporting 11–12px — OK
- **Issues:** TopHeader still shows Demo toggle + RUNNING pill (state OK); locale commas in tab prices (`4.394,55`)

### Dashboard BTCUSD (`design-audit-btcusd.png`)
- **Primary focus:** CLEAR — `WAIT` + MTF −25.68 (different from XAU → no stale leak)
- **Density:** same shell
- **Responsive:** not mobile-captured (CDP resize unavailable)

### Positions
- Filter + summary strip; honest closed empty state
- Was over-carded → densified to inline metrics

### Strategy (`design-audit-strategy.png` pre-densify)
- Still had Card + indicator pills in first capture → refactored to separators
- RESEARCH ONLY badge kept (allowed state)

### Trading / Risk / Backtest / Mobile
- Trading reuses decision panel (same primary pattern)
- Risk/Backtest still use some MetricCard/Card patterns — secondary backlog
- Mobile: not auto-resized; layout uses stack + horizontal symbol scroll by design

## Checklist

| Check | Result |
|-------|--------|
| Too many cards on overview? | Mostly gone |
| Too many borders? | Separators only on primary path |
| Equal visual weight? | Decision primary; account tertiary |
| Badge rainbow? | Outline / state only |
| M15 prominent? | PRIMARY + stronger weight |
| Scan in ~3s? | Yes on XAU SHORT |
| Marketing hero? | Removed |
| Operational empty copy? | Kept |

## Remaining (not blocking)

1. Densify Risk / Backtest / Paper MetricCard grids
2. Optional: remove nav icons (still icon+label)
3. Force `en-US` tabular price formatting in SymbolTabs
4. Mobile viewport screenshot when browser resize available

## Market data visual language (CMC-inspired)

Follow-up to TasteSkill densify — restore financial density without card bloat.

### Preserved / restored

- Symbol tabs: price + session abs/% move (baseline = first mid in browser session)
- Active tab: surface + bottom indicator + stronger price
- Decision: large price, MarketMove, M15 dark primary block, HTF secondary tiles
- Account: Today PnL money + `dailyReturnPct` when backend flags available
- Positions: unrealized money + entry→current price-move % (not capital ROI)
- DEMO/LIVE segmented control: high-contrast selected state
- Buttons: stronger primary/secondary/ghost hierarchy

### Honesty constraints

- Session % ≠ 24h CMC (documented domain formula)
- Position % = price move vs entry by direction (tooltip clarifies)
- No fabricated % when baseline/entry unavailable
