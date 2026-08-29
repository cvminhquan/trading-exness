# Historical Data Export (Phase 7.2A)

This document describes how to export XAUUSD (or other symbol) historical OHLCV
data from a connected Exness MetaTrader 5 terminal for use in Phase 7 backtests.

The exporter is a **read-only data tool**. It never places, modifies, or closes
orders and does not interact with the trading engine.

---

## Prerequisites

1. **Windows** with MetaTrader 5 installed (Exness account).
2. MT5 terminal **running and logged in**.
3. Python environment with project dependencies installed.
4. Optional MT5 package: `pip install MetaTrader5` (Windows only).

Configure credentials in `.env`:

```env
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=Exness-MT5Trial
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

Optional export defaults:

```env
HISTORICAL_SYMBOL=XAUUSD
HISTORICAL_START=2023-01-01
HISTORICAL_END=2026-08-29
```

`HISTORICAL_START` and `HISTORICAL_END` are **not** silently applied by the CLI;
you must pass `--start` and `--end`, or set both environment variables.

---

## Export command

```bash
python -m exness_bot.tools.export_history \
  --symbol XAUUSD \
  --timeframe M15 \
  --start 2023-01-01 \
  --end 2026-08-29
```

Optional output path:

```bash
python -m exness_bot.tools.export_history \
  --symbol XAUUSD \
  --timeframe M15 \
  --start 2023-01-01 \
  --end 2026-08-29 \
  --output data/historical/XAUUSD_M15.csv
```

If the broker symbol differs (e.g. `XAUUSDm`), the exporter resolves the actual
name and writes `data/historical/XAUUSDm_M15.csv` by default.

---

## Export at least 20,000 M15 candles

M15 produces up to ~96 bars per 24h session. For **≥20,000 candles**, export
roughly **10+ months** of history. A safe command:

```bash
python -m exness_bot.tools.export_history \
  --symbol XAUUSD \
  --timeframe M15 \
  --start 2022-06-01 \
  --end 2026-08-29
```

This range (~4 years) should yield well over 20,000 bars on Exness XAUUSD M15.

After export, run the baseline:

```bash
exness-bot baseline
```

---

## Supported timeframes

| Timeframe | MT5 constant |
|-----------|-------------|
| M1        | 1           |
| M5        | 5           |
| M15       | 15          |
| M30       | 30          |
| H1        | 16385       |
| H4        | 16388       |
| D1        | 16408       |

Phase 7 baseline requires **M15**.

---

## CSV schema

Default output: `data/historical/{broker_symbol}_{timeframe}.csv`

| Column        | Description                                      |
|---------------|--------------------------------------------------|
| timestamp     | ISO-8601 UTC (e.g. `2024-01-01T00:00:00+00:00`) |
| open          | Bar open price                                   |
| high          | Bar high price                                   |
| low           | Bar low price                                    |
| close         | Bar close price                                  |
| tick_volume   | Tick volume from MT5                             |
| spread        | Spread in points (MT5 history field)             |
| real_volume   | Real volume when provided by broker              |

The backtest loader accepts `tick_volume` as volume when `volume` is absent.

Example:

```csv
timestamp,open,high,low,close,tick_volume,spread,real_volume
2024-01-01T00:00:00+00:00,2350.0,2352.0,2348.0,2351.0,100,20,0
```

---

## Timezone behavior

- MT5 bar open times are converted to **UTC**.
- CSV timestamps are written as timezone-aware ISO strings (`+00:00`).
- The backtest loader parses all timestamps as UTC.

---

## Gap handling

After export, the tool reports:

| Metric                 | Description                                |
|------------------------|--------------------------------------------|
| Normal session gaps    | Weekends, daily market pauses (≤4h weekday)|
| Unexpected data gaps   | Long weekday gaps outside expected sessions|
| Duplicate count        | Repeated timestamps                        |
| OHLC validity          | high ≥ low, open/close within range        |
| Spread min/avg/max     | From MT5 history spread field              |

Normal weekend/market-closed gaps **do not fail** the export.

---

## Symbol resolution

The exporter does not assume the broker symbol is exactly `XAUUSD`:

1. Try exact symbol via `symbol_info`.
2. Search all terminal symbols for prefix/contains match.
3. If exactly one match → use it.
4. If zero or multiple matches → error with suggested symbol names.

Set `HISTORICAL_SYMBOL` or `--symbol` to your preferred query string.

---

## Reproducibility

To reproduce an export:

1. Use the same MT5 server and symbol.
2. Record the exact command and date range.
3. Re-run the same command; MT5 may append newer bars if `--end` is today.

Example recorded run:

```bash
python -m exness_bot.tools.export_history \
  --symbol XAUUSD \
  --timeframe M15 \
  --start 2022-06-01 \
  --end 2026-08-29 \
  --output data/historical/XAUUSD_M15.csv
```

---

## Troubleshooting

| Error | Action |
|-------|--------|
| MT5 terminal not connected | Open MT5 and log in |
| Symbol not found | Check `--symbol`; review suggested matches |
| No historical data | Widen date range; verify symbol in Market Watch |
| Start/end required | Pass `--start` and `--end` explicitly |

---

## Safety guarantee

`HistoricalExporter` only uses read-only MT5 APIs:

- `initialize`, `login`, `shutdown`
- `symbol_info`, `symbol_select`, `symbols_get`
- `copy_rates_range`, `copy_rates_from`

It **never** calls `order_send`, `positions_get` for trading, or modifies account state.
