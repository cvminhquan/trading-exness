import type {
  BacktestAssumptions,
  BacktestDataset,
  BacktestExecutionConfig,
  BacktestPerformance,
  BacktestReport,
  BacktestTradeRecord,
  EquityPoint,
} from "@/domain";
import {
  BACKTEST_DATASET,
  getDatasetQualityStatus,
} from "@/lib/constants/backtest";
import {
  buildRAnalysis,
  deriveDrawdownCurve,
  deriveMonthlyPerformance,
} from "@/lib/backtest/derive";

/** Set to [] to test the NO_REPORT empty state. */
export const MOCK_BACKTEST_REPORTS: BacktestReport[] = [];

const STRATEGY = "ema_rsi_atr_v1";
const SYMBOL = "XAUUSD";
const TIMEFRAME = "M15";

const EXECUTION: BacktestExecutionConfig = {
  initialBalance: 10_000,
  riskPerTradePct: 0.5,
  maxDailyLossPct: 2.0,
  maxDrawdownPct: 5.0,
  maxOpenPositions: 1,
  maxPositionLots: 0.5,
  spreadPoints: 50,
  slippagePoints: 1,
  commissionPerLot: 3.5,
  swapPerLotPerDay: -1.2,
  warmupBars: 200,
};

const ASSUMPTIONS: BacktestAssumptions = {
  candleTiming: "Tín hiệu được đánh giá khi nến đóng (M15)",
  execution: "Vào lệnh tại giá đóng nến tín hiệu, có áp dụng spread + trượt giá",
  spread: "Cố định 50 points mỗi phía",
  slippage: "Cố định 1 point bất lợi khi vào và thoát lệnh",
  commission: "$3.50 mỗi lot khớp hai chiều",
  swap: "-$1.20 mỗi lot mỗi ngày (qua đêm)",
  exitCosts: "Phí hoa hồng + phí qua đêm trừ khỏi PnL gộp",
  positionLimit: "Tối đa 1 vị thế mở; khối lượng theo rủi ro 0,5% vốn",
  endOfData: "Vị thế mở được đóng tại nến cuối, có trừ chi phí thoát lệnh",
  positionSizing: "Rủi ro cố định 0,5% mỗi giao dịch (khoảng cách cắt lỗ theo ATR)",
  sameBarExitRule:
    "SL/TP được đánh giá từ nến tiếp theo; cùng nến SL+TP → Cắt lỗ trước",
};

const buildDataset = (params: {
  totalCandles: number;
  start: string;
  end: string;
  durationDays: number;
  isMeaningful: boolean;
  duplicateTimestamps?: number;
  missingPeriods?: number;
}): BacktestDataset => ({
  totalCandles: params.totalCandles,
  startTimestamp: params.start,
  endTimestamp: params.end,
  durationDays: params.durationDays,
  timezone: "UTC",
  duplicateTimestamps: params.duplicateTimestamps ?? 0,
  missingPeriods: params.missingPeriods ?? 0,
  missingBarsTotal: params.missingPeriods ?? 0,
  weekendGaps: Math.floor(params.durationDays / 7) * 2,
  sessionGaps: 0,
  isSorted: true,
  isValidOhlc: true,
  isMeaningful: params.isMeaningful,
  minRequiredCandles: BACKTEST_DATASET.minMeaningfulCandles,
  recommendedCandles: BACKTEST_DATASET.recommendedCandles,
  qualityStatus: getDatasetQualityStatus(params.totalCandles, params.isMeaningful),
});

/** Deterministic pseudo-random for reproducible mock trades. */
const seeded = (seed: number): number => {
  const x = Math.sin(seed * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
};

const generateTrades = (count: number, startMs: number): BacktestTradeRecord[] => {
  const trades: BacktestTradeRecord[] = [];

  for (let i = 0; i < count; i += 1) {
    const r = seeded(i + 1);
    const direction: "LONG" | "SHORT" = r > 0.52 ? "LONG" : "SHORT";
    const entryBase = 2280 + Math.sin(i / 8) * 45 + seeded(i * 3) * 20;
    const atr = 3.5 + seeded(i * 5) * 2;
    const stopDistance = atr * 1.5;
    const stopLoss =
      direction === "LONG" ? entryBase - stopDistance : entryBase + stopDistance;
    const takeProfit =
      direction === "LONG"
        ? entryBase + stopDistance * (1.2 + seeded(i * 7) * 1.5)
        : entryBase - stopDistance * (1.2 + seeded(i * 7) * 1.5);

    const winBias = 0.46 + Math.sin(i / 15) * 0.04;
    const isWin = seeded(i * 11) < winBias;
    const exitReason = isWin ? "take_profit" : "stop_loss";
    const exitPrice = isWin ? takeProfit : stopLoss;
    const volume = 0.05 + seeded(i * 13) * 0.07;
    const grossMove =
      direction === "LONG" ? exitPrice - entryBase : entryBase - exitPrice;
    const grossPnl = Math.round(grossMove * volume * 100 * 100) / 100;
    const commission = Math.round(EXECUTION.commissionPerLot * volume * 2 * 100) / 100;
    const swap =
      seeded(i * 17) > 0.7
        ? Math.round(EXECUTION.swapPerLotPerDay * volume * 100) / 100
        : 0;
    const netPnl = Math.round((grossPnl - commission - swap) * 100) / 100;

    const entryOffsetHours = Math.floor(i * 36 + seeded(i) * 12);
    const barsHeld = 4 + Math.floor(seeded(i * 19) * 20);
    const entryTime = new Date(startMs + entryOffsetHours * 3_600_000).toISOString();
    const exitTime = new Date(
      startMs + (entryOffsetHours + barsHeld) * 3_600_000,
    ).toISOString();

    const risk = Math.abs(entryBase - stopLoss);
    const move =
      direction === "LONG" ? exitPrice - entryBase : entryBase - exitPrice;
    const rMultiple = risk > 0 ? Math.round((move / risk) * 100) / 100 : null;

    trades.push({
      tradeId: i + 1,
      direction,
      volume: Math.round(volume * 100) / 100,
      entryPrice: Math.round(entryBase * 100) / 100,
      exitPrice: Math.round(exitPrice * 100) / 100,
      stopLoss: Math.round(stopLoss * 100) / 100,
      takeProfit: Math.round(takeProfit * 100) / 100,
      entryTime,
      exitTime,
      exitReason,
      grossPnl,
      commission,
      swap,
      netPnl,
      barsHeld,
      rMultiple,
      signalReason: "Tín hiệu EMA stack + vùng RSI khi nến M15 đóng",
    });
  }

  return trades;
};

const computePerformance = (
  trades: BacktestTradeRecord[],
  equityCurve: EquityPoint[],
): BacktestPerformance => {
  const winners = trades.filter((t) => t.netPnl > 0);
  const losers = trades.filter((t) => t.netPnl < 0);
  const grossProfit = winners.reduce((s, t) => s + t.grossPnl, 0);
  const grossLoss = Math.abs(losers.reduce((s, t) => s + t.grossPnl, 0));
  const netProfit = trades.reduce((s, t) => s + t.netPnl, 0);
  const totalCommission = trades.reduce((s, t) => s + t.commission, 0);
  const totalSwap = trades.reduce((s, t) => s + t.swap, 0);
  const initialBalance = EXECUTION.initialBalance;
  const finalBalance = initialBalance + netProfit;

  let maxConsecutiveWins = 0;
  let maxConsecutiveLosses = 0;
  let streakW = 0;
  let streakL = 0;
  for (const t of trades) {
    if (t.netPnl > 0) {
      streakW += 1;
      streakL = 0;
    } else if (t.netPnl < 0) {
      streakL += 1;
      streakW = 0;
    }
    maxConsecutiveWins = Math.max(maxConsecutiveWins, streakW);
    maxConsecutiveLosses = Math.max(maxConsecutiveLosses, streakL);
  }

  const drawdownSeries = deriveDrawdownCurve(equityCurve);
  const maxDrawdownPct = Math.max(...drawdownSeries.map((d) => d.equity), 0);
  const maxDrawdownUsd = Math.round((maxDrawdownPct / 100) * initialBalance * 100) / 100;
  const currentDrawdownPct = drawdownSeries[drawdownSeries.length - 1]?.equity ?? 0;

  const rValues = trades
    .map((t) => t.rMultiple)
    .filter((r): r is number => r !== null);

  return {
    totalTrades: trades.length,
    winningTrades: winners.length,
    losingTrades: losers.length,
    winRate: trades.length ? (winners.length / trades.length) * 100 : 0,
    grossProfit: Math.round(grossProfit * 100) / 100,
    grossLoss: Math.round(grossLoss * 100) / 100,
    netProfit: Math.round(netProfit * 100) / 100,
    totalCommission: Math.round(totalCommission * 100) / 100,
    totalSwap: Math.round(totalSwap * 100) / 100,
    profitFactor:
      grossLoss > 0 ? Math.round((grossProfit / grossLoss) * 100) / 100 : null,
    expectancy: trades.length ? netProfit / trades.length : 0,
    averageWin: winners.length
      ? winners.reduce((s, t) => s + t.netPnl, 0) / winners.length
      : 0,
    averageLoss: losers.length
      ? losers.reduce((s, t) => s + t.netPnl, 0) / losers.length
      : 0,
    averageTrade: trades.length ? netProfit / trades.length : null,
    averageR: rValues.length
      ? rValues.reduce((s, r) => s + r, 0) / rValues.length
      : null,
    largestWin: winners.length
      ? Math.max(...winners.map((t) => t.netPnl))
      : null,
    largestLoss: losers.length ? Math.min(...losers.map((t) => t.netPnl)) : null,
    maxConsecutiveWins,
    maxConsecutiveLosses,
    initialBalance,
    finalBalance: Math.round(finalBalance * 100) / 100,
    returnPct: Math.round((netProfit / initialBalance) * 10000) / 100,
    maxDrawdownPct: Math.round(maxDrawdownPct * 100) / 100,
    maxDrawdownUsd,
    maxDrawdownDurationBars: 48,
    currentDrawdownPct: Math.round(currentDrawdownPct * 100) / 100,
    averageTradeDurationBars: trades.length
      ? Math.round(trades.reduce((s, t) => s + t.barsHeld, 0) / trades.length)
      : null,
  };
};

const buildEquityCurveFromTrades = (
  trades: BacktestTradeRecord[],
  barCount: number,
  startMs: number,
): EquityPoint[] => {
  const curve: EquityPoint[] = [];
  let equity = EXECUTION.initialBalance;
  let tradeIdx = 0;
  const sortedTrades = [...trades].sort(
    (a, b) => new Date(a.exitTime).getTime() - new Date(b.exitTime).getTime(),
  );

  for (let bar = 0; bar < barCount; bar += 1) {
    const ts = new Date(startMs + bar * 15 * 60_000).toISOString();
    while (
      tradeIdx < sortedTrades.length &&
      new Date(sortedTrades[tradeIdx]?.exitTime ?? 0).getTime() <=
        new Date(ts).getTime()
    ) {
      equity += sortedTrades[tradeIdx]?.netPnl ?? 0;
      tradeIdx += 1;
    }
    equity += Math.sin(bar / 120) * 8;
    curve.push({
      timestamp: ts,
      equity: Math.round(equity * 100) / 100,
    });
  }
  return curve;
};

const buildCompletedReport = (): BacktestReport => {
  const periodStart = "2022-06-01T00:00:00.000Z";
  const periodEnd = "2026-08-29T23:59:59.000Z";
  const startMs = new Date(periodStart).getTime();
  const totalCandles = 21_840;
  const trades = generateTrades(142, startMs);
  const equityCurve = buildEquityCurveFromTrades(trades, 480, startMs);
  const drawdownCurve = deriveDrawdownCurve(equityCurve);
  const performance = computePerformance(trades, equityCurve);
  const monthlyPerformance = deriveMonthlyPerformance(trades).map((m) => ({
    ...m,
    returnPct:
      performance.initialBalance > 0
        ? Math.round((m.netPnl / performance.initialBalance) * 10000) / 100
        : null,
  }));
  const rAnalysis = buildRAnalysis(trades);

  return {
    id: "baseline-completed-1",
    strategy: STRATEGY,
    symbol: SYMBOL,
    timeframe: TIMEFRAME,
    status: "completed",
    generatedAt: "2026-08-28T14:30:00.000Z",
    message: null,
    periodStart,
    periodEnd,
    dataset: buildDataset({
      totalCandles,
      start: periodStart,
      end: periodEnd,
      durationDays: 1551,
      isMeaningful: true,
    }),
    execution: EXECUTION,
    performance,
    assumptions: ASSUMPTIONS,
    classification: {
      classification: "PROMISING BUT INSUFFICIENT",
      rationale: [
        "Lợi nhuận ròng dương trên toàn bộ mẫu với drawdown được kiểm soát.",
        "Tỷ lệ thắng gần 46% — kỳ vọng lợi nhuận nhờ mục tiêu R không đối xứng.",
        "Mẫu bao phủ nhiều chế độ biến động nhưng vẫn chỉ một symbol/khung thời gian.",
        "Chỉ dùng cho mục đích nghiên cứu — chưa được xác thực cho triển khai live.",
      ],
    },
    equityCurve,
    drawdownCurve,
    trades,
    monthlyPerformance,
    rAnalysis,
  };
};

const buildInsufficientReport = (): BacktestReport => ({
  id: "baseline-insufficient-1",
  strategy: STRATEGY,
  symbol: SYMBOL,
  timeframe: TIMEFRAME,
  status: "insufficient_data",
  generatedAt: "2026-08-28T14:35:00.000Z",
  message:
    "Không có file CSV lịch sử XAUUSD M15 trong repository. Bộ dữ liệu dưới ngưỡng mẫu tối thiểu có ý nghĩa.",
  periodStart: null,
  periodEnd: null,
  dataset: buildDataset({
    totalCandles: 1_200,
    start: "2026-07-01T00:00:00.000Z",
    end: "2026-08-29T23:59:59.000Z",
    durationDays: 60,
    isMeaningful: false,
    missingPeriods: 14,
  }),
  execution: EXECUTION,
  performance: null,
  assumptions: ASSUMPTIONS,
  classification: {
    classification: "INSUFFICIENT DATA — NO CLASSIFICATION",
    rationale: [
      "Tổng số nến (1.200) dưới mức tối thiểu yêu cầu (5.000).",
      "Các chỉ số hiệu suất được cố ý không hiển thị.",
      "Xuất dữ liệu lịch sử qua công cụ export_history của trading-engine.",
    ],
  },
  equityCurve: [],
  drawdownCurve: [],
  trades: [],
  monthlyPerformance: [],
  rAnalysis: null,
});

export const mockBacktestCompleted = buildCompletedReport();
export const mockBacktestInsufficient = buildInsufficientReport();

/** Default mock list — set MOCK_BACKTEST_REPORTS = [] for NO_REPORT testing. */
if (MOCK_BACKTEST_REPORTS.length === 0) {
  MOCK_BACKTEST_REPORTS.push(mockBacktestCompleted, mockBacktestInsufficient);
}

export const mockBacktestReports = MOCK_BACKTEST_REPORTS;
