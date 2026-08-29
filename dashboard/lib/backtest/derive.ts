import type { BacktestTradeRecord, EquityPoint, MonthlyPerformance } from "@/domain";

/** Derive percentage drawdown series from equity curve (display only — does not mutate source). */
export const deriveDrawdownCurve = (equityCurve: EquityPoint[]): EquityPoint[] => {
  if (!equityCurve.length) return [];

  let peak = equityCurve[0]?.equity ?? 0;
  return equityCurve.map((point) => {
    peak = Math.max(peak, point.equity);
    const drawdownPct = peak > 0 ? ((peak - point.equity) / peak) * 100 : 0;
    return {
      timestamp: point.timestamp,
      equity: Math.round(drawdownPct * 100) / 100,
    };
  });
};

/** Derive monthly buckets from trade exit timestamps and net PnL. */
export const deriveMonthlyPerformance = (
  trades: BacktestTradeRecord[],
): MonthlyPerformance[] => {
  const buckets = new Map<
    string,
    { netPnl: number; trades: number; wins: number }
  >();

  for (const trade of trades) {
    const month = trade.exitTime.slice(0, 7);
    const existing = buckets.get(month) ?? { netPnl: 0, trades: 0, wins: 0 };
    existing.netPnl += trade.netPnl;
    existing.trades += 1;
    if (trade.netPnl > 0) existing.wins += 1;
    buckets.set(month, existing);
  }

  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, stats]) => ({
      month,
      netPnl: Math.round(stats.netPnl * 100) / 100,
      returnPct: null,
      trades: stats.trades,
      winRate: stats.trades > 0 ? (stats.wins / stats.trades) * 100 : 0,
    }));
};

/** Downsample for chart rendering only — underlying report data stays intact. */
export const downsampleForChart = <T>(data: T[], maxPoints = 500): T[] => {
  if (data.length <= maxPoints) return data;
  const step = Math.ceil(data.length / maxPoints);
  const sampled = data.filter((_, index) => index % step === 0);
  const last = data[data.length - 1];
  if (last && sampled[sampled.length - 1] !== last) {
    sampled.push(last);
  }
  return sampled;
};

export const computeRMultiple = (trade: BacktestTradeRecord): number | null => {
  const risk = Math.abs(trade.entryPrice - trade.stopLoss);
  if (risk <= 0) return null;
  const move =
    trade.direction === "LONG"
      ? trade.exitPrice - trade.entryPrice
      : trade.entryPrice - trade.exitPrice;
  return Math.round((move / risk) * 100) / 100;
};

export const buildRAnalysis = (trades: BacktestTradeRecord[]) => {
  const rValues = trades
    .map((t) => t.rMultiple ?? computeRMultiple(t))
    .filter((r): r is number => r !== null);

  if (!rValues.length) {
    return {
      averageR: null,
      winningRAverage: null,
      losingRAverage: null,
      bestR: null,
      worstR: null,
      rMultiples: [] as number[],
    };
  }

  const winners = rValues.filter((r) => r > 0);
  const losers = rValues.filter((r) => r < 0);

  return {
    averageR: rValues.reduce((s, r) => s + r, 0) / rValues.length,
    winningRAverage: winners.length
      ? winners.reduce((s, r) => s + r, 0) / winners.length
      : null,
    losingRAverage: losers.length
      ? losers.reduce((s, r) => s + r, 0) / losers.length
      : null,
    bestR: Math.max(...rValues),
    worstR: Math.min(...rValues),
    rMultiples: rValues,
  };
};
