# Exness Trading Bot

Modular, testable algorithmic trading engine for **Exness** via **MetaTrader 5**.

> **Safety first:** Defaults to `TRADING_MODE=demo` and `DRY_RUN=true`. Live trading requires explicit configuration flags.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical architecture |
| [docs/TRADING_RULES.md](docs/TRADING_RULES.md) | Strategy & risk rules |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Implementation roadmap |

## Quick Start

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies (Linux/macOS — MT5 optional)
pip install -e ".[dev]"

# Windows: include MT5 adapter dependencies
# pip install -e ".[dev,mt5]"

# Copy environment template
cp .env.example .env

# Run tests
pytest

# Lint & type check
ruff check src tests
mypy src
```

## Read-only HTTP API (Phase 10.5–10.6)

Dashboard integration via FastAPI — **read-only**, không mutation endpoints.

```bash
# Install API dependencies
pip install -e ".[api,dev]"

# Mock mode (Linux default)
DATA_SOURCE=mock exness-bot-api

# MT5 live read-only (Windows + terminal)
DATA_SOURCE=mt5 MT5_ENABLED=true exness-bot-api

# Health: http://127.0.0.1:8000/health
# OpenAPI: http://127.0.0.1:8000/docs
```

Xem [docs/MT5_READ_ONLY.md](../docs/MT5_READ_ONLY.md) cho chi tiết MT5 adapter.

Configure Dashboard:

```bash
# dashboard/.env.local
NEXT_PUBLIC_DATA_SOURCE=api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Architecture Overview

```
Market Data → Strategy → Signal → Risk Manager → Order Manager → MT5
```

- Strategy never places orders directly
- Risk Manager can reject valid signals
- Order Manager is the only module that submits orders
- MT5 integration isolated behind `BrokerPort`

## Project Status

**v0.1.0 — Foundation:** Documentation, project structure, domain models, safety guards, and tooling. Full trading logic not yet implemented.

See [docs/ROADMAP.md](docs/ROADMAP.md) for next steps.

## License

MIT
