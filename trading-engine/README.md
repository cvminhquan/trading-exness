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

### Windows (PowerShell) — khuyến nghị khi dùng MT5

```powershell
py -3.12 -m venv .venv
# Không có 3.12: py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,dev,mt5]"
Copy-Item .env.example .env
pytest
ruff check src tests
mypy src
```

Nếu bị chặn `Activate.ps1`:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux / macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
cp .env.example .env
pytest
ruff check src tests
mypy src
```

## Read-only HTTP API (Phase 10.5–10.6)

Dashboard tích hợp qua FastAPI — chủ yếu **đọc**, không phải CLI đặt lệnh tự do.

```powershell
# Cài dependency API (Windows)
pip install -e ".[api,dev,mt5]"

# Chạy API (sau khi đã Activate.ps1)
exness-bot-api
# hoặc: python -m exness_bot.api
```

```bash
# Linux/macOS — mock (không cần MT5 terminal)
pip install -e ".[api,dev]"
DATA_SOURCE=mock exness-bot-api

# Windows + MT5 terminal — đọc dữ liệu thật
# DATA_SOURCE=mt5 và MT5_ENABLED=true trong .env
exness-bot-api
```

- Health: http://127.0.0.1:8000/health
- OpenAPI: http://127.0.0.1:8000/docs


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
