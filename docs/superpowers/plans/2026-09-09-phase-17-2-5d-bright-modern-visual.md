# PHASE 17.2.5D Bright Modern Visual Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brighten and modernize the dashboard visual system with Financial Blue brand tokens while keeping multi-symbol behavior, data semantics, and execution/broker safety unchanged.

**Architecture:** Token-first soft workstation — update `globals.css` semantic tokens first, detach M15 from `--accent`, then restyle shell → account → tabs → hero → setup/risk → reasons → positions → chart. Visual verification via browser screenshots at 1440/1920 (and mobile).

**Tech Stack:** Next.js dashboard, Tailwind v4 + CSS variables, existing Recharts `RealizedPnlChart`, existing `MtfScoreBar` (diverging −100…+100).

**Spec:** `docs/superpowers/specs/2026-09-09-phase-17-2-5d-bright-modern-visual-design.md`

## Global Constraints

- Visual/frontend only; strategy / research / ExecutionCandidate / execution architecture unchanged
- Broker mutation: NO; no `order_send`; no new trading controls
- Blue = brand/interaction only; green/red = financial semantics only
- Detach M15 from `--accent` **before** or in the same change that sets `--accent: #2563EB`
- No fabricated % (chart header: sum `$` only); no sparkline without series
- Risk flags independent (broker / riskAcceptable / eligibility)
- `negative-subtle` reasons only when truly BLOCKED
- CURRENT price marker = neutral/foreground, not brand blue by default
- TP1_ONLY hierarchy in Setup UI
- Commits: only when the user explicitly asks (do not auto-commit)
- UI copy Vietnamese; technical IDs English
- Verification: `npm run typecheck` + `npm run lint` in `dashboard/`; screenshot review required before “done”

## File map

| File | Responsibility |
|------|----------------|
| `dashboard/app/globals.css` | Canonical + deprecated alias tokens |
| `dashboard/components/layout/DashboardShell.tsx` | Sidebar active rail (no shift), accent active |
| `dashboard/components/layout/TopHeader.tsx` | Sticky depth, status strip clarity |
| `dashboard/components/layout/AccountSwitcher.tsx` | Brand primary for real profile switch; never execution toggle |
| `dashboard/components/shared/BotStatusIndicator.tsx` | Status ≠ button |
| `dashboard/components/ui/button.tsx` | Primary accent / secondary / ghost |
| `dashboard/components/account/AccountOverviewSection.tsx` | Metric hierarchy |
| `dashboard/components/market/SymbolTabs.tsx` | Active underline + scrollIntoView |
| `dashboard/components/trading-analysis/TradeDecisionHero.tsx` | Hero + M15 surface + HTF + wire `MtfScoreBar` |
| `dashboard/components/trading-analysis/MtfScoreBar.tsx` | Diverging bar visual refresh |
| `dashboard/components/trading-analysis/TradeSetupCard.tsx` | Blocks + TP1 prominence |
| `dashboard/components/trading-analysis/PriceRelationshipBar.tsx` | Neutral CURRENT marker |
| `dashboard/components/trading-analysis/RiskAssessmentCard.tsx` | Number-first + independent statuses |
| `dashboard/components/trading-analysis/DecisionReasonsCard.tsx` | Semantic tint by state |
| `dashboard/components/trading-analysis/MultiTimeframeDetails.tsx` | Accordion summary rows |
| `dashboard/components/trading-analysis/TimeframeAnalysisAccordion.tsx` | Row density/hover |
| `dashboard/components/positions/PositionTable.tsx` | Table density |
| `dashboard/components/account/RealizedPnlChart.tsx` | Header sum $, taller chart, token colors |
| `docs/PHASE_17_2_5D_VISUAL_REDESIGN.md` | Screenshot acceptance notes (after review) |

---

### Task 1: Design tokens (+ M15 detach prerequisite note)

**Files:**
- Modify: `dashboard/app/globals.css`
- Modify: `dashboard/components/trading-analysis/TradeDecisionHero.tsx` (only the M15 container classes that use `bg-[var(--accent)]` — must not remain accent-bound when Task 1 lands)

**Interfaces:**
- Produces: CSS variables listed in spec Section 1; legacy aliases with `@deprecated` comments

- [ ] **Step 1: Replace `:root` token block** with approved shape (`--surface-active: var(--accent-subtle)`, semantic `*-subtle`, `--shadow-xs`, deprecated aliases mapping `--text-primary` → `--foreground`, `--surface-muted` → `--surface-subtle`, etc.)

- [ ] **Step 2: Immediately change M15 block** in `TradeDecisionHero.tsx` from `bg-[var(--accent)] text-white` to `bg-[var(--surface-subtle)]` + semantic border/tint placeholders (full M15 polish in Task 6) so accent blue never paints M15

- [ ] **Step 3: Update `*:focus-visible`** to use `var(--accent)`

- [ ] **Step 4: Verify**

```bash
cd dashboard && npm run typecheck && npm run lint
```

Expected: PASS

---

### Task 2: Shell / Sidebar / Header / Buttons / Status

**Files:**
- Modify: `dashboard/components/layout/DashboardShell.tsx`
- Modify: `dashboard/components/layout/TopHeader.tsx`
- Modify: `dashboard/components/layout/AccountSwitcher.tsx`
- Modify: `dashboard/components/shared/BotStatusIndicator.tsx`
- Modify: `dashboard/components/ui/button.tsx`

**Interfaces:**
- Consumes: tokens from Task 1
- Produces: active nav without layout shift; primary button = accent

- [ ] **Step 1: Sidebar** — always reserve 3px left border (`border-l-[3px] border-transparent` inactive; `border-[var(--accent)]` active) **or** absolute inset rail that does not change padding; active `bg-[var(--surface-active)]`; hover `surface-hover`

- [ ] **Step 2: Header** — sticky surface + border + `box-shadow: var(--shadow-xs)`; keep title left; status right as dots/text

- [ ] **Step 3: AccountSwitcher compact** — selected segment uses accent (real profile API); ensure copy/aria still account environment, not execution mode

- [ ] **Step 4: BotStatusIndicator / ConnectionIndicator** — outline/dot chips, not button variants

- [ ] **Step 5: button.tsx** — `default` → `bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white`; `outline` → white + `border-[var(--border-strong)]`; `ghost` → transparent + hover surface; focus ring accent

- [ ] **Step 6: typecheck + lint**

---

### Task 3: Account Summary

**Files:**
- Modify: `dashboard/components/account/AccountOverviewSection.tsx`

- [ ] **Step 1: Keep column order** Today PnL → Equity → Balance → Margin → Positions; secondary strip underneath

- [ ] **Step 2: Typography** — Today PnL value `text-[20px]`–`text-[22px]`; others `text-[18px]`–`text-[20px]`; labels 12–13px muted; no icons

- [ ] **Step 3: Surface** — single `bg-[var(--surface)]`; no five nested cards

- [ ] **Step 4: typecheck + lint**

---

### Task 4: Symbol Tabs

**Files:**
- Modify: `dashboard/components/market/SymbolTabs.tsx`

- [ ] **Step 1: Active styling** — `bg-[var(--surface-active)]` + `border-b-[3px] border-[var(--accent)]`; symbol/price remain `text-[var(--foreground)]`; LONG/SHORT semantic colors only

- [ ] **Step 2: Mobile** — keep `overflow-x-auto`; `whitespace` so tab content does not wrap into chaotic two lines

- [ ] **Step 3: scrollIntoView** — `useEffect` / ref on active `Link` calling `scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" })` when `activeSymbol` changes

- [ ] **Step 4: typecheck + lint**

---

### Task 5: Trading Hero chrome

**Files:**
- Modify: `dashboard/components/trading-analysis/TradeDecisionHero.tsx`

- [ ] **Step 1: Ensure hero** is white surface; price `text-[32px]`–`text-[36px]`; signal/MTF `text-[26px]`–`text-[30px]`; no full-hero accent fill

- [ ] **Step 2: MTF SCORE** tile uses `surface-subtle`; score color by sign only

- [ ] **Step 3: typecheck + lint**

---

### Task 6: M15 + HTF + diverging bar

**Files:**
- Modify: `dashboard/components/trading-analysis/TradeDecisionHero.tsx`
- Modify: `dashboard/components/trading-analysis/MtfScoreBar.tsx`

**Interfaces:**
- Reuse existing `MtfScoreBar({ score })` with engine thresholds from `mtf-display`

- [ ] **Step 1: Restyle `MtfScoreBar`** — labels ≥12px where important; center 0 visible; wait zone between SHORT/LONG thresholds; marker at score position; use token colors (not slate hardcodes); **not** a left-to-right progress fill of the score

- [ ] **Step 2: M15 panel** — `surface-subtle` + border; if bearish `border-l`/`bg` with `negative-subtle`; if bullish `positive-subtle`; large score; bias label; render `<MtfScoreBar score={m15.score.totalScore} />`

- [ ] **Step 3: HTF cells** — H1 stronger than H4/D1 (type size / contrast)

- [ ] **Step 4: typecheck + lint**

---

### Task 7: Setup / Price relationship / Risk

**Files:**
- Modify: `dashboard/components/trading-analysis/TradeSetupCard.tsx`
- Modify: `dashboard/components/trading-analysis/PriceRelationshipBar.tsx`
- Modify: `dashboard/components/trading-analysis/RiskAssessmentCard.tsx`

- [ ] **Step 1: Setup blocks** — ENTRY ZONE / CURRENT / SL as stacked value blocks; TP1 large + label execution target (use existing `L.executionTarget`); TP2/TP3 secondary + analysis label

- [ ] **Step 2: PriceRelationshipBar** — CURRENT marker `bg-[var(--foreground)]` (or neutral), labels ≥12px; entry zone range visible; no default accent on CURRENT

- [ ] **Step 3: Risk** — top stack: budget / estimated / volume as large numbers + small labels; then three status rows driven independently:
  - `sizing.brokerExecutable`
  - `sizing.riskAcceptable`
  - eligibility from `eligibility?.eligible` / `analysis.executionAssessment` (do not derive blocked from the first two)

- [ ] **Step 4: typecheck + lint**

---

### Task 8: Reasons / Accordion

**Files:**
- Modify: `dashboard/components/trading-analysis/DecisionReasonsCard.tsx`
- Modify: `dashboard/components/trading-analysis/MultiTimeframeDetails.tsx`
- Modify: `dashboard/components/trading-analysis/TimeframeAnalysisAccordion.tsx`

- [ ] **Step 1: Reasons tint** — `bg-[var(--negative-subtle)]` only if `isBlocked`; WAITING_FOR_ENTRY → `warning-subtle` or neutral; WAIT without block → not full negative

- [ ] **Step 2: Technical details** — text button; hover toward accent; raw codes collapsed

- [ ] **Step 3: MultiTimeframeDetails** — when collapsed, show compact summary rows for M15/H1/H4/D1 (score + bias) + expand control; when open, existing accordion; row height ~40–44px; hover `surface-hover`; focus accent

- [ ] **Step 4: typecheck + lint**

---

### Task 9: Positions table

**Files:**
- Modify: `dashboard/components/positions/PositionTable.tsx`
- Modify: `dashboard/components/ui/table.tsx` (if shared density)

- [ ] **Step 1: Rows ~44–48px; body 14px; header stronger contrast**

- [ ] **Step 2: PnL money + % priority; direction compact semantic; numeric columns right + tabular**

- [ ] **Step 3: typecheck + lint**

---

### Task 10: Realized PnL chart

**Files:**
- Modify: `dashboard/components/account/RealizedPnlChart.tsx`

- [ ] **Step 1: Header** — title + `formatCurrency(sum(data.map(d => d.realizedPnl)))` when data present; **do not** show invented %

- [ ] **Step 2: Chart** — height ~220–260px; axis ticks ≥12px; grid use `var(--border)`; bar fills `var(--positive)` / `var(--negative)`

- [ ] **Step 3: typecheck + lint**

---

### Task 11: Responsive pass

**Files:**
- Modify as needed: overview `dashboard/app/dashboard/[symbol]/page.tsx`, `TradeAnalysisSection.tsx`, SymbolTabs (from Task 4)

- [ ] **Step 1: Confirm mobile stack order** matches spec (tabs → decision → setup/risk → reasons → positions → account → chart) without reordering architecture beyond CSS/grid

- [ ] **Step 2: Spot-check tablet** decision hierarchy preserved

- [ ] **Step 3: typecheck + lint**

---

### Task 12: Visual screenshot review (acceptance)

**Files:**
- Create/Update: `docs/PHASE_17_2_5D_VISUAL_REDESIGN.md`

- [ ] **Step 1: Browser** — open `/dashboard/XAUUSD` and another symbol at ~1440 and ~1920 widths; capture hero, tabs, account, positions, chart

- [ ] **Step 2: Checklist** from spec (brightness, accent restraint, M15 not blue, readable type, BLOCKED tint only when blocked, chart $ only, DEMO ≠ execution)

- [ ] **Step 3: If still pale/monotonous or AI-admin** — iterate tokens/components before marking complete

- [ ] **Step 4: Write short audit doc** with components changed, tokens changed, screens reviewed, backend/strategy/execution: NONE

---

## Plan self-review

| Spec area | Task |
|-----------|------|
| Tokens + aliases + subtle + shadow | 1 |
| M15 detach before blue accent | 1 |
| Shell/header/buttons/status | 2 |
| Account | 3 |
| Symbol tabs + scrollIntoView | 4 |
| Hero | 5 |
| M15 + diverging bar + HTF | 6 |
| Setup TP1 / CURRENT marker / Risk independence | 7 |
| Reasons tint / accordion | 8 |
| Positions | 9 |
| Chart sum $ no % | 10 |
| Responsive | 11 |
| Screenshot review | 12 |

No TBD placeholders. Commit steps omitted pending user request.
