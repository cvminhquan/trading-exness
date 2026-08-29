# Exness Trading

Monorepo for the **Exness algorithmic trading system** — Python trading engine + Next.js operations dashboard.

## Structure

```
exness-trading/
├── trading-engine/     # Python — MT5 algorithmic trading engine
├── dashboard/          # Next.js — monitoring & analytics dashboard
├── docs/               # Shared product & architecture documentation
├── .gitignore
└── README.md
```

## Trading Engine

See [trading-engine/README.md](trading-engine/README.md).

```bash
cd trading-engine
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
pytest
exness-bot-api   # read-only API on :8000
```

## Dashboard

See [dashboard/README.md](dashboard/README.md).

```bash
cd dashboard
npm install
npm run dev
```

Open [http://localhost:3000/dashboard](http://localhost:3000/dashboard).

**Data source:** `NEXT_PUBLIC_DATA_SOURCE=mock` (default) or `api` with API running at `NEXT_PUBLIC_API_BASE_URL`.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/TRADING_RULES.md](docs/TRADING_RULES.md) | Strategy & risk rules |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Implementation roadmap |

Engine-specific docs live under `trading-engine/docs/`.
# trading-exness
