# PHASE 17.2.5D — Bright Modern Visual Redesign

**Date:** 2026-09-09  
**Status:** Design APPROVED · Final visual direction updated (white canvas + rounded cards)  
**Approach:** Token-first modern fintech workstation (cards for semantic groups)  
**Accent:** Financial Blue `#2563EB` (brand / interaction only)

## Direction update (supersedes soft-flat gray canvas)

- App background: **white** (`#FFFFFF`), not large gray `#F4F7FB`
- Cards **encouraged** for meaningful groups (Account, Symbols, Analysis, Setup, Risk, Positions, Chart)
- Soft `--shadow-card`, radius ~12–16px
- Interactive hover elevation only on interactive surfaces
- See also: `docs/PHASE_17_2_5D_VISUAL_REDESIGN.md` (implementation audit)

## Non-goals (safety)

- No strategy / research scoring / ExecutionCandidate / execution architecture changes
- No real trading controls; no `order_send`; **broker mutation: NO**
- No fabricated market/% data; no sparkline without historical series
- Frontend visual only; preserve multi-symbol routes and API/data layer

## Visual goal

Bright, modern, financial, professional, high-contrast, data-rich.  
CMC-level clarity + professional trading workstation identity.  
Not: gray admin template, AI SaaS, dark cyberpunk, neon crypto, card soup, glassmorphism, gradients.

---

## Section 1 — Color / token system (APPROVED)

### Canonical tokens

```css
--background: #F4F7FB;

--surface: #FFFFFF;
--surface-subtle: #F8FAFC;
--surface-hover: #F1F5F9;
--surface-active: var(--accent-subtle); /* alias — do not duplicate hex */

--border: #E2E8F0;
--border-strong: #CBD5E1;

--foreground: #0F172A;
--foreground-secondary: #334155;
--muted: #64748B;

--accent: #2563EB;
--accent-hover: #1D4ED8;
--accent-subtle: #EFF6FF;
--accent-muted: #DBEAFE;

--positive: /* emerald family */;
--positive-subtle: /* light emerald tint for alert/bg */;

--negative: /* rose/red family */;
--negative-subtle: /* light rose tint */;

--warning: /* amber family */;
--warning-subtle: /* light amber tint */;

--shadow-xs: /* very light elevation — sticky header / true floating only */;
```

Suggested semantic hex (implementation may tune ±1 step within family):

| Token | Value |
|-------|--------|
| `--positive` | `#059669` |
| `--positive-subtle` | `#ECFDF5` |
| `--negative` | `#E11D48` |
| `--negative-subtle` | `#FFF1F2` |
| `--warning` | `#D97706` |
| `--warning-subtle` | `#FFFBEB` |
| `--shadow-xs` | `0 1px 0 rgba(15, 23, 42, 0.04)` |

### Rules

1. Blue = brand / interaction only (nav active, symbol indicator, primary button, focus, links, selected filters, chart chrome).
2. Green/red = financial semantics only (PnL, LONG/SHORT, score sign). Never green for active nav.
3. Prefer `*-subtle` tokens over ad-hoc opacity for alert backgrounds.
4. `--shadow-xs` is not default card elevation.
5. **Legacy aliases** (`--text-primary`, `--text-secondary`, `--text-muted`, `--surface-muted`, etc.) map to new tokens with `@deprecated` comments — migrate gradually, do not maintain two independent hex systems.

### Critical migration order

**Detach M15 PRIMARY from `bg-[var(--accent)]` before swapping `--accent` to blue.**  
M15 is a semantic analysis surface, not a brand surface.

### Typography scale

| Role | Size |
|------|------|
| Main price | 32–36px |
| Signal / MTF score | 26–30px |
| Account main metrics | 18–22px (Today PnL ≤22px; must not outrank hero) |
| Section heading | 15–16px |
| Body / table | 14px |
| Supporting | 12–13px |

Important UI ≥12px. Financial numbers: `tabular-nums`.

---

## Section 2 — Shell + Account + Symbol tabs (APPROVED)

### Sidebar

- Surface on cool background; rows 40–44px; text 14–15px; icons ~18px
- Active: `surface-active` + **3px accent left rail** + strong foreground / semibold
- **No layout shift:** rail via reserved `border-l` / inset pseudo always present (transparent when inactive)
- Hover: `surface-hover`; no giant pills

### Header

- Sticky: surface + border + **optional `--shadow-xs` only here**
- Left: Trading Bot / page title
- Right: environment + status strip (dot + text for MT5 / Running — not fake buttons)
- **DEMO control:** keep as interactive **account profile** switcher only if backend-supported (`AccountSwitcher` / set active account). Must not read as execution DEMO↔LIVE toggle. LIVE remains confirmed. If ever non-functional, render as status not switch.

### Account summary

Order (no icons):

```
TODAY PNL     EQUITY      BALANCE     MARGIN LEVEL   POSITIONS
+$…           $…          $…          …%             N
+…%   (when dailyReturnAvailable)

Used Margin …  Unrealized …  Realized …
```

- One white surface, not five cards
- Today PnL strongest among account metrics (20–22px) but weaker than hero price/signal

### Symbol tabs

- SYMBOL · optional SHORT/LONG (semantic) · PRICE (neutral) · abs/% (semantic)
- Active: `surface-active` + 2–3px **bottom** accent only; symbol/price stay foreground neutral
- Inactive readable; hover clear
- Desktop: current density; mobile: horizontal scroll, no messy wrap; **scroll active tab into view** on route change
- No sparkline (no series)

---

## Section 3 — Hero / M15 / Setup·Risk / Reasons / Positions·Chart (APPROVED)

### Trading Hero

- White/light surface; no full-hero blue tint
- Optional tiny accent detail only (e.g. hairline) — not a banner
- Price 32–36px neutral; SELL/SHORT / BUY/LONG semantic; WAIT neutral
- MTF SCORE on `surface-subtle`, score 26–30px by sign

### M15 PRIMARY (must leave `--accent`)

- `surface-subtle` + light border; optional `positive-subtle` / `negative-subtle` by bias
- Strong score; medium bias label
- **Diverging score bar (−100…+100)** with visible **center 0** and wait zone around 0; marker at score — **not** a L→R progress bar
- H1 medium; H4/D1 contextual — not identical cells

### Setup

- Information blocks (label muted / value strong), not settings form
- **TP1** dominant: value + `EXECUTION TARGET` (current plan TP1_ONLY)
- **TP2 / TP3** secondary: smaller + `Analysis`
- Price relationship: TP1 ── CURRENT ── [ENTRY ZONE] ── SL
  - **CURRENT marker:** strong foreground / neutral marker (data, not interaction). Blue only if interactive (hover/tooltip/selection)

### Risk

- Prominent: risk budget, estimated risk, proposed volume (numbers first)
- Compact status rows with ✓/✕
- **Three independent flags from backend:** Broker executable · Risk acceptable · Execution eligibility/blocked — **do not infer** blocked from the other two

### Reasons

- `negative-subtle` panel **only when truly BLOCKED**
- `WAITING_FOR_ENTRY` / waiting: `warning-subtle` or neutral — not “system failure” red
- WAIT without setup: neutral / warning-subtle as appropriate
- Operator bullets in Vietnamese; raw codes under collapsed Technical details (text action)

### Timeframe accordion

- Collapsed state still shows row summaries (TF · score · bias · chevron); no dead blank
- Row ~40–44px; hover; focus `--accent`

### Positions

- Header stronger; rows 44–48px; 14px; PnL $ + % scannable; direction compact semantic
- Tabular right-aligned numerics; subtle row hover; light horizontal rules

### Realized PnL · 7 days

- Header: title + **sum($)** of daily realized if API semantics = daily realized PnL
- **No %** without a defined baseline (do not invent sum/balance %)
- Taller chart; clearer axes/grid/tooltip
- Bar fills: semantic green/red; brand blue only for interaction chrome if needed

### Buttons

- Primary safe = accent / accent-hover  
- Secondary = white + border-strong  
- Ghost / text = transparent, clear hover  
- Status ≠ button  

### Motion

- Fast, restrained: hover, tab active, accordion, button press, tooltip/chart hover  
- No flashy motion  

### Responsive

- Desktop dense workstation (1440 / 1920 review required)
- Tablet: preserve decision hierarchy
- Mobile order: Symbol tabs → Price → Signal → M15 → Setup → Risk → Reasons → Positions → Account → PnL  

---

## Gate review (2026-09-09)

| Gate | Result | Notes |
|------|--------|-------|
| Consistency | PASS | Blue interaction vs green/red semantics; M15 detached from accent; aliases deprecated |
| Accessibility | PASS | Focus ring accent; ≥12px; reserved sidebar rail; status vs controls; accordion affordance |
| Responsive | PASS | Tab scroll-into-view; mobile stack order; no tab wrap chaos |
| Data semantics | PASS | No fake % on chart; session move only; TP1_ONLY hierarchy; risk flags independent; CURRENT marker not brand |
| Safety | PASS | Visual-only; no strategy/execution/broker mutation |

**Gate: PASS** → proceed to implementation plan.

## Spec self-review

- No TBD/TODO placeholders in requirements
- Sections 1–3 + six lock-in fixes included
- Scope is single visual phase; no strategy subsystem mixed in
- Ambiguities resolved: CURRENT marker, diverging M15 bar, risk independence, reasons tint, chart $ only, TP1 prominence

## Files expected to change (implementation)

- `dashboard/app/globals.css` — tokens
- `dashboard/components/layout/DashboardShell.tsx`, `TopHeader.tsx`, `AccountSwitcher.tsx` (visual/clarity only)
- `dashboard/components/account/AccountOverviewSection.tsx`, `RealizedPnlChart.tsx`
- `dashboard/components/market/SymbolTabs.tsx`
- `dashboard/components/trading-analysis/*` (Hero, Setup, Risk, Reasons, PriceRelationshipBar, MultiTimeframeDetails / accordion)
- `dashboard/components/positions/PositionTable.tsx`
- `dashboard/components/ui/button.tsx` (+ badge/status if still button-like)
- Optional: small presentational helper for M15 diverging bar
- Docs: this spec + plan; optional audit note after screenshots

**Backend / strategy / execution: NONE**
