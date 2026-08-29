# Exness Trading Bot Dashboard

Next.js operations dashboard for monitoring the Exness algorithmic trading system.

**Phase 10.1 MVP** — mock data only, no live order execution.

## Stack

- Next.js (App Router)
- TypeScript
- Tailwind CSS
- React Query
- Zod
- Recharts

## Development

```bash
npm install
npm run dev
```

Routes:

- `/dashboard` — Overview
- `/dashboard/positions`
- `/dashboard/trades`
- `/dashboard/strategy`
- `/dashboard/risk`
- `/dashboard/backtest`
- `/dashboard/settings`

## Architecture

```
domain/          → Zod schemas & TypeScript types
repositories/    → TradingRepository interface + MockTradingRepository
queries/         → React Query hooks
mocks/           → Static mock data
components/      → Reusable UI by feature area
app/dashboard/   → Route pages
```

Replace `MockTradingRepository` with `ApiTradingRepository` when the backend API is ready — UI components stay unchanged.

## Validation

```bash
npm run lint
npm run build
```
