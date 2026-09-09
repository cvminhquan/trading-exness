"""Macro observation models for free external sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Documented BLS series IDs (Public Data API) — do NOT invent IDs.
# Official meanings (BLS):
#   CUUR0000SA0     — CPI-U All items, U.S. city average, not seasonally adjusted
#   CUUR0000SA0L1E  — CPI-U All items less food and energy (Core CPI), NSA
#   LNS14000000     — Unemployment Rate, 16 years and over, seasonally adjusted
#   CES0000000001   — All employees, total nonfarm, seasonally adjusted (thousands)
BLS_SERIES: dict[str, dict[str, str]] = {
    "CUUR0000SA0": {
        "name": "CPI-U All items (NSA)",
        "category": "inflation",
        "unit": "index",
    },
    "CUUR0000SA0L1E": {
        "name": "Core CPI-U less food and energy (NSA)",
        "category": "inflation",
        "unit": "index",
    },
    "LNS14000000": {
        "name": "Unemployment Rate (SA)",
        "category": "labor",
        "unit": "percent",
    },
    "CES0000000001": {
        "name": "Total nonfarm payroll employment (SA)",
        "category": "labor",
        "unit": "thousands",
    },
}

# Documented FRED series — only when FRED_API_KEY configured.
# Official meanings (FRED / Treasury / Fed H.10):
#   DGS10     — Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity
#   DGS2      — Market Yield on U.S. Treasury Securities at 2-Year Constant Maturity
#   DTWEXBGS  — Nominal Broad U.S. Dollar Index
FRED_SERIES: dict[str, dict[str, str]] = {
    "DGS10": {
        "name": "10-Year Treasury Constant Maturity Rate",
        "category": "yields",
        "unit": "percent",
    },
    "DGS2": {
        "name": "2-Year Treasury Constant Maturity Rate",
        "category": "yields",
        "unit": "percent",
    },
    "DTWEXBGS": {
        "name": "Nominal Broad U.S. Dollar Index",
        "category": "usd",
        "unit": "index",
    },
}


@dataclass
class MacroObservation:
    provider: str
    series_id: str
    name: str
    category: str
    value: float
    published_at: str | None
    retrieved_at: str
    canonical_url: str | None
    unit: str | None = None
    previous_value: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def delta(self) -> float | None:
        if self.previous_value is None:
            return None
        return self.value - self.previous_value
