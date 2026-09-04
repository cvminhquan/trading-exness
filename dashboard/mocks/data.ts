import type {
  AccountSnapshot,
  BotStatus,
  DashboardOverview,
  EquityPoint,
  Position,
  RiskSnapshot,
  SessionContext,
  StrategySignal,
  StrategySnapshot,
  SystemSettings,
  Trade,
  Quote,
  PaperTrading,
} from "@/domain";

const now = new Date();
const iso = (offsetHours: number): string =>
  new Date(now.getTime() - offsetHours * 3_600_000).toISOString();

export const mockBotStatus: BotStatus = "RUNNING";

export const mockSession: SessionContext = {
  tradingMode: "DEMO",
  connectionStatus: "CONNECTED",
  accountLabel: "Demo #12345678",
  botStatus: mockBotStatus,
  accountProfile: "demo",
  candleEngine: {
    status: "STOPPED",
    lastProcessedAt: null,
    lastClosedAt: null,
    lastUpdateAt: null,
    dataSource: "MOCK",
  },
  signalEngine: {
    status: "STOPPED",
    strategy: "ema_rsi_atr_v1",
    lastProcessedCandle: null,
    lastSignal: null,
    lastSignalAt: null,
    dataSource: "MOCK",
  },
  paperExecution: {
    status: "STOPPED",
    mode: "paper",
    balance: 10_000,
    equity: 10_000,
    openPositions: 0,
    lastExecution: null,
    lastExecutionAt: null,
  },
};

export const mockAccount: AccountSnapshot = {
  balance: 10_842.5,
  equity: 10_956.3,
  todayPnl: 124.8,
  totalPnl: 842.5,
  drawdownPct: 1.82,
  margin: 412.0,
  freeMargin: 10_544.3,
  currency: "USD",
  updatedAt: iso(0),
  profit: 113.8,
  leverage: 500,
  marginLevel: 2659.3,
};

const buildEquityCurve = (points = 90): EquityPoint[] => {
  const result: EquityPoint[] = [];
  let equity = 10_000;
  for (let i = points; i >= 0; i -= 1) {
    equity += Math.sin(i / 4) * 18 + (i % 7 === 0 ? -22 : 4);
    result.push({
      timestamp: iso(i * 8),
      equity: Math.round(equity * 100) / 100,
    });
  }
  return result.reverse();
};

export const mockEquityCurve = buildEquityCurve();

export const mockPositions: Position[] = [
  {
    id: "pos-1",
    symbol: "XAUUSD",
    direction: "LONG",
    volume: 0.12,
    entryPrice: 2348.5,
    currentPrice: 2354.2,
    stopLoss: 2336.0,
    takeProfit: 2373.0,
    unrealizedPnl: 68.4,
    rMultiple: 0.48,
    openedAt: iso(18),
    swap: -0.12,
  },
];

export const mockTrades: Trade[] = [
  {
    id: "tr-105",
    closedAt: iso(2),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "LONG",
    entryPrice: 2339.2,
    exitPrice: 2351.8,
    volume: 0.1,
    grossPnl: 126.0,
    costs: 4.2,
    netPnl: 121.8,
    rMultiple: 1.85,
    commission: 0,
    swap: 0,
    exitReason: "take_profit",
  },
  {
    id: "tr-104",
    closedAt: iso(8),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "SHORT",
    entryPrice: 2358.4,
    exitPrice: 2352.1,
    volume: 0.08,
    grossPnl: 50.4,
    costs: 3.6,
    netPnl: 46.8,
    rMultiple: 0.92,
    commission: 0,
    swap: 0,
    exitReason: "take_profit",
  },
  {
    id: "tr-103",
    closedAt: iso(26),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "SHORT",
    entryPrice: 2362.0,
    exitPrice: 2368.4,
    volume: 0.08,
    grossPnl: -51.2,
    costs: 3.8,
    netPnl: -55.0,
    rMultiple: -1.02,
    commission: 0,
    swap: 0,
    exitReason: "stop_loss",
  },
  {
    id: "tr-102",
    closedAt: iso(40),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "LONG",
    entryPrice: 2326.5,
    exitPrice: 2326.5,
    volume: 0.05,
    grossPnl: 0,
    costs: 2.1,
    netPnl: -2.1,
    rMultiple: 0,
    commission: 0,
    swap: 0,
    exitReason: "manual",
  },
  {
    id: "tr-101",
    closedAt: iso(50),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "LONG",
    entryPrice: 2318.4,
    exitPrice: 2329.6,
    volume: 0.1,
    grossPnl: 112.0,
    costs: 4.0,
    netPnl: 108.0,
    rMultiple: 1.42,
    commission: 0,
    swap: 0,
    exitReason: "take_profit",
  },
  {
    id: "tr-100",
    closedAt: iso(72),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "LONG",
    entryPrice: 2305.1,
    exitPrice: 2301.3,
    volume: 0.09,
    grossPnl: -34.2,
    costs: 3.5,
    netPnl: -37.7,
    rMultiple: -0.76,
    commission: 0,
    swap: 0,
    exitReason: "stop_loss",
  },
  {
    id: "tr-99",
    closedAt: iso(96),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "SHORT",
    entryPrice: 2310.8,
    exitPrice: 2304.2,
    volume: 0.07,
    grossPnl: 46.2,
    costs: 3.2,
    netPnl: 43.0,
    rMultiple: 0.88,
    commission: 0,
    swap: 0,
    exitReason: "take_profit",
  },
  {
    id: "tr-98",
    closedAt: iso(120),
    symbol: "XAUUSD",
    strategy: "ema_rsi_atr_v1",
    direction: "LONG",
    entryPrice: 2298.0,
    exitPrice: 2291.5,
    volume: 0.1,
    grossPnl: -65.0,
    costs: 4.0,
    netPnl: -69.0,
    rMultiple: -1.15,
    commission: 0,
    swap: 0,
    exitReason: "stop_loss",
  },
];

const buyConditions = [
  {
    id: "ema-stack",
    label: "Sắp xếp EMA",
    detail: "EMA20 > EMA50 > EMA200",
    satisfied: true,
  },
  {
    id: "rsi-zone",
    label: "Vùng RSI Long",
    detail: "RSI14 = 61.4 (50–70)",
    satisfied: true,
  },
  {
    id: "atr-stop",
    label: "Khoảng cách cắt lỗ ATR",
    detail: "ATR14 = 3.82 — trong giới hạn sizing",
    satisfied: true,
  },
];

export const mockCurrentSignal: StrategySignal = {
  symbol: "XAUUSD",
  strategy: "ema_rsi_atr_v1",
  action: "BUY",
  direction: "LONG",
  timestamp: iso(0.25),
  indicators: {
    ema20: 2349.2,
    ema50: 2342.8,
    ema200: 2328.5,
    rsi14: 61.4,
    atr14: 3.82,
  },
  reason: "Điều kiện xu hướng và momentum thỏa mãn khi nến M15 đóng.",
  conditions: buyConditions,
  summary: "Tín hiệu nghiên cứu — không phải lệnh đã khớp.",
};

export const mockRecentSignals: StrategySignal[] = [
  mockCurrentSignal,
  {
    ...mockCurrentSignal,
    action: "HOLD",
    direction: "FLAT",
    timestamp: iso(4),
    reason: "Đang chờ nến M15 tiếp theo đóng.",
    conditions: buyConditions.map((c) => ({ ...c, satisfied: c.id !== "rsi-zone" })),
    summary: "Chưa có tín hiệu hành động mới; đang theo dõi xu hướng.",
  },
  {
    ...mockCurrentSignal,
    action: "SELL",
    direction: "SHORT",
    timestamp: iso(20),
    reason: "Phát hiện setup Short nhưng bị chặn bởi risk manager.",
    conditions: [
      {
        id: "ema-stack",
        label: "Sắp xếp EMA",
        detail: "EMA20 < EMA50 — thiên hướng Short",
        satisfied: true,
      },
      {
        id: "risk-block",
        label: "Risk manager",
        detail: "Đã đạt số vị thế mở tối đa",
        satisfied: false,
      },
    ],
    summary: "Tín hiệu bị từ chối — giới hạn rủi ro đang hoạt động.",
  },
];

export const mockStrategy: StrategySnapshot = {
  id: "ema_rsi_atr_v1",
  name: "ema_rsi_atr_v1",
  symbol: "XAUUSD",
  timeframe: "M15",
  status: "RUNNING",
  currentSignal: mockCurrentSignal,
  recentSignals: mockRecentSignals,
};

export const mockRisk: RiskSnapshot = {
  equity: mockAccount.equity,
  riskPerTradePct: 0.5,
  updatedAt: iso(0),
  limits: [
    {
      key: "daily_loss",
      label: "Lỗ trong ngày",
      category: "daily",
      configuredLimit: 200,
      currentValue: 120,
      unit: "currency",
    },
    {
      key: "drawdown",
      label: "Drawdown",
      category: "drawdown",
      configuredLimit: 5.0,
      currentValue: 1.82,
      unit: "percent",
    },
    {
      key: "open_positions",
      label: "Vị thế đang mở",
      category: "exposure",
      configuredLimit: 1,
      currentValue: 1,
      unit: "count",
    },
    {
      key: "position_risk",
      label: "Rủi ro vị thế",
      category: "trade",
      configuredLimit: 0.5,
      currentValue: 0.5,
      unit: "percent",
    },
    {
      key: "exposure",
      label: "Mức phơi nhiễm",
      category: "exposure",
      configuredLimit: 1.0,
      currentValue: 0.12,
      unit: "lots",
    },
    {
      key: "equity",
      label: "Vốn tài khoản",
      category: "account",
      configuredLimit: 10_000,
      currentValue: mockAccount.equity,
      unit: "currency",
    },
  ],
};

export { mockBacktestReports } from "./backtest-data";

export const mockSettings: SystemSettings = {
  tradingMode: "DRY_RUN",
  broker: "Exness MT5",
  symbol: "XAUUSD",
  timeframe: "M15",
  strategy: "ema_rsi_atr_v1",
  riskPerTradePct: 0.5,
  maxDailyLossPct: 2.0,
  maxDrawdownPct: 5.0,
  maxOpenPositions: 1,
};

export const mockDashboardOverview: DashboardOverview = {
  botStatus: mockBotStatus,
  account: mockAccount,
  equityCurve: mockEquityCurve,
  positions: mockPositions,
  recentTrades: mockTrades.slice(0, 5),
  currentSignal: mockCurrentSignal,
};

export const mockQuotes: Quote[] = [
  { symbol: "XAUUSD", bid: 4456.32, ask: 4456.48, last: 4456.40, spread: 0.16, digits: 2, available: true, updatedAt: iso(0), freshness: "LIVE" },
  { symbol: "EURUSD", bid: 1.16814, ask: 1.16826, last: 1.16820, spread: 0.00012, digits: 5, available: true, updatedAt: iso(0), freshness: "LIVE" },
  { symbol: "GBPUSD", bid: 1.34204, ask: 1.34216, last: 1.34210, spread: 0.00012, digits: 5, available: true, updatedAt: iso(0), freshness: "LIVE" },
  { symbol: "USDJPY", bid: 147.845, ask: 147.859, last: 147.852, spread: 0.014, digits: 3, available: true, updatedAt: iso(0), freshness: "LIVE" },
  { symbol: "XAGUSD", bid: 38.24, ask: 38.26, last: 38.25, spread: 0.02, digits: 3, available: true, updatedAt: iso(0), freshness: "LIVE" },
  { symbol: "BTCUSD", bid: 108440, ask: 108460, last: 108450, spread: 20, digits: 2, available: true, updatedAt: iso(0), freshness: "LIVE" },
  { symbol: "ETHUSD", bid: 4279.2, ask: 4280.8, last: 4280.0, spread: 1.6, digits: 2, available: true, updatedAt: iso(0), freshness: "LIVE" },
];

export const simulateDelay = (ms = 350): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

export const mockPaperTrading: PaperTrading = {
  status: "STOPPED",
  mode: "paper",
  researchOnly: true,
  accountKind: "paper",
  sessionId: "paper-mock-session",
  startedAt: iso(24),
  initialBalance: 10_000,
  balance: 10_094.4,
  equity: 10_106.9,
  realizedPnl: 94.4,
  unrealizedPnl: 12.5,
  dailyPnl: 106.9,
  drawdownPct: 0,
  openPositions: 1,
  executionCount: 2,
  signalCount: 2,
  candlesProcessed: 3,
  rejectedCount: 0,
  lastExecution: "FILLED",
  lastExecutionAt: iso(6),
  lastSignal: "BUY",
  positions: [
    {
      positionId: "paper-pos-2",
      symbol: "XAUUSD",
      side: "LONG",
      volume: 0.16,
      entryPrice: 2350.31,
      currentPrice: 2351.1,
      stopLoss: 2347.31,
      takeProfit: 2356.31,
      unrealizedPnl: 12.5,
      openedAt: iso(2),
      status: "OPEN",
    },
  ],
  trades: [
    {
      time: iso(6),
      symbol: "XAUUSD",
      side: "LONG",
      volume: 0.16,
      entry: 2350.31,
      stopLoss: 2347.31,
      takeProfit: 2356.31,
      exit: 2356.2,
      pnl: 94.4,
      status: "CLOSED",
      reason: "TP",
    },
    {
      time: iso(2),
      symbol: "XAUUSD",
      side: "LONG",
      volume: 0.16,
      entry: 2350.31,
      stopLoss: 2347.31,
      takeProfit: 2356.31,
      exit: null,
      pnl: 12.5,
      status: "OPEN",
      reason: null,
    },
  ],
};
