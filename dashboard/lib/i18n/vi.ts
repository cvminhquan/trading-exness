/** Nhãn hiển thị tiếng Việt — giá trị domain/enum giữ nguyên tiếng Anh. */

export const UI = {
  appName: "Trading Bot",
  appSubtitle: "Bảng điều khiển vận hành thuật toán Exness",
  navigation: "Điều hướng",
  navigationSubtitle: "Giám sát & phân tích",
  menu: "Menu",
  mockData: "Dữ liệu mẫu",
  liveData: "Nguồn API",
  readOnly: "Chỉ đọc",
  retry: "Thử lại",
  loading: "Đang tải...",
  noData: "Chưa có dữ liệu",
  noDataDescription:
    "Khi trading engine được kết nối, mục này sẽ tự động cập nhật.",
  errorGeneric: "Đã xảy ra lỗi không mong muốn.",
  errorLoad: "Không thể tải dữ liệu",
  errorLoadSection: (section: string) => `Không thể tải ${section}`,
  all: "Tất cả",
  from: "Từ",
  to: "Đến",
  search: "Tìm kiếm",
  currentLimit: "Hiện tại / Giới hạn",
  utilization: "Mức sử dụng",
  researchOnly: "Chỉ dùng cho mục đích nghiên cứu",
  historicalSimulation: "Mô phỏng lịch sử",
  backtestBadge: "BACKTEST · MÔ PHỎNG LỊCH SỬ",
  drawdownMaxHint: "Giới hạn tối đa cấu hình 5%",
  tradeJournal: "Nhật ký giao dịch",
  filterJournal: "Lọc nhật ký",
  symbolOrTradeId: "Symbol hoặc mã giao dịch",
  symbol: "Symbol",
  direction: "Hướng",
  strategy: "Chiến lược",
  result: "Kết quả",
  winners: "Thắng",
  losers: "Thua",
  showingTrades: (filtered: number, total: number) =>
    `Hiển thị ${filtered} / ${total} giao dịch · lọc phía client`,
  activeStrategy: "Chiến lược đang hoạt động",
  indicatorSnapshot: "Ảnh chụp chỉ báo",
  recentSignals: "Tín hiệu gần đây",
  conditions: "Điều kiện",
  summary: "Tóm tắt",
  time: "Thời gian",
  action: "Hành động",
  entry: "Giá vào lệnh",
  exit: "Giá thoát lệnh",
  currentPrice: "Giá hiện tại",
  bid: "Bid",
  ask: "Ask",
  last: "Last",
  spread: "Spread",
  live: "Realtime",
  quoteUnavailable: "Không có trên broker",
  dataLive: "Dữ liệu live",
  dataStale: "Dữ liệu cũ",
  dataUnavailable: "Không khả dụng",
  volume: "Khối lượng",
  gross: "PnL gộp",
  costs: "Chi phí",
  netPnl: "PnL ròng",
  exitReason: "Lý do thoát",
  duration: "Thời lượng",
  equityCurve: "Đường cong vốn",
  noEquityData: "Chưa có dữ liệu vốn",
  noEquityDataDescription:
    "Lịch sử vốn sẽ hiển thị khi có snapshot tài khoản từ trading engine.",
  initial: "Ban đầu",
  equityLabel: "Vốn chủ sở hữu",
  noDrawdownData: "Chưa có dữ liệu Drawdown",
  noDrawdownDataDescription:
    "Lịch sử Drawdown sẽ được tính khi có đủ snapshot vốn.",
  current: "Hiện tại",
  max: "Tối đa",
  riskPerTradeHint: "Quy tắc sizing vị thế đã cấu hình",
  riskWarnCrit: (warn: number, crit: number) => `cảnh báo ${warn}% / nguy hiểm ${crit}%`,
  riskUtilizationAria: (label: string, pct: string) => `Mức sử dụng ${label}: ${pct}%`,
  settingsConfigDisabled:
    "Thay đổi cấu hình bị vô hiệu hóa trong MVP này. Giá trị phản ánh cấu hình hiện tại của trading engine.",
} as const;

export const ACCOUNT_SWITCH = {
  title: "Tài khoản MT5",
  description:
    "Chọn tài khoản demo hoặc thật để xem số dư và vị thế. Bot vẫn không được phép đặt lệnh.",
  demo: "Demo",
  live: "Thật",
  demoFull: "Tài khoản demo",
  liveFull: "Tài khoản thật (chỉ đọc)",
  switching: "Đang chuyển tài khoản...",
  confirmTitle: "Chuyển sang tài khoản thật?",
  confirmBody:
    "Dashboard sẽ đăng nhập MT5 vào tài khoản thật để xem dữ liệu. Bot không đặt lệnh. Terminal MT5 trên máy cũng sẽ chuyển sang tài khoản này.",
  confirm: "Chuyển sang tài khoản thật",
  cancel: "Giữ tài khoản demo",
  liveNotConfigured:
    "Chưa cấu hình tài khoản thật. Thêm MT5_LIVE_LOGIN, MT5_LIVE_PASSWORD và MT5_LIVE_SERVER vào file .env của trading-engine, rồi khởi động lại API.",
  demoNotConfigured: "Chưa cấu hình tài khoản demo.",
  login: "Login",
  server: "Server",
  notConfigured: "Chưa cấu hình",
  switchFailed: "Không thể chuyển tài khoản.",
} as const;

export const EMPTY = {
  noOpenPositions: "Không có vị thế đang mở",
  noOpenPositionsOverview:
    "Khi Bot mở giao dịch, mức phơi nhiễm đang hoạt động sẽ hiển thị tại đây cùng giá vào lệnh, rủi ro và PnL chưa thực hiện.",
  noOpenPositionsPage:
    "Bot không có mức phơi nhiễm thị trường đang hoạt động. Lệnh vào mới sẽ xuất hiện sau khi chiến lược và risk manager chấp thuận tín hiệu.",
  noRecentTrades: "Chưa có giao dịch gần đây",
  noRecentTradesDescription:
    "Các giao dịch đã đóng từ nhật ký sẽ hiển thị tại đây sau khi khớp lệnh.",
  noTradesMatchFilters: "Không có giao dịch khớp bộ lọc",
  noTradesMatchFiltersDescription:
    "Điều chỉnh bộ lọc hoặc chờ trading engine ghi nhận giao dịch đã đóng vào nhật ký.",
} as const;

export const SETTINGS = {
  groups: {
    broker: "Broker",
    tradingMode: "Chế độ giao dịch",
    market: "Thị trường",
    strategy: "Chiến lược",
    risk: "Rủi ro",
    account: "Tài khoản MT5",
  },
  labels: {
    tradingMode: "Chế độ giao dịch",
    broker: "Broker",
    symbol: "Symbol",
    timeframe: "Khung thời gian",
    strategy: "Chiến lược",
    riskPerTrade: "Rủi ro mỗi giao dịch",
    maxDailyLoss: "Lỗ tối đa trong ngày",
    maxDrawdown: "Drawdown tối đa",
    maxOpenPositions: "Số vị thế mở tối đa",
  },
} as const;

export const SECTION_LABELS = {
  overview: "tổng quan",
  quotes: "giá thị trường",
  positions: "vị thế",
  trades: "giao dịch",
  strategy: "chiến lược",
  risk: "rủi ro",
  settings: "cài đặt",
  paper: "paper trading",
} as const;

export const NAV = {
  overview: { label: "Tổng quan", description: "Theo dõi sức khỏe Bot, hiệu suất tài khoản và mức phơi nhiễm hiện tại." },
  positions: {
    label: "Vị thế",
    description: "Vị thế thật trên Exness (BROKER ACCOUNT). Không gồm vị thế giấy.",
  },
  trades: { label: "Giao dịch", description: "Xem lại các giao dịch đã thực hiện và hiệu suất giao dịch." },
  strategy: { label: "Chiến lược", description: "Kiểm tra trạng thái chiến lược và tín hiệu hiện tại." },
  risk: { label: "Rủi ro", description: "Theo dõi giới hạn rủi ro và mức phơi nhiễm tài khoản." },
  backtest: { label: "Backtest", description: "Phân tích mô phỏng chiến lược trên dữ liệu lịch sử." },
  paper: {
    label: "Paper Trading",
    description: "Khớp lệnh ảo PAPER ONLY — không gửi lệnh tới Exness.",
  },
  settings: { label: "Cài đặt", description: "Xem cấu hình hệ thống giao dịch." },
} as const;

export const BOT_STATUS_LABELS = {
  RUNNING: "Đang chạy",
  STOPPED: "Đã dừng",
  ERROR: "Lỗi",
  DISCONNECTED: "Mất kết nối",
} as const;

export const BOT_STATUS_DESCRIPTIONS = {
  RUNNING: "Bot đang hoạt động và xử lý nến đóng",
  STOPPED: "Bot đã được dừng có chủ đích",
  ERROR: "Bot gặp lỗi và tạm dừng",
  DISCONNECTED: "Bot không thể kết nối terminal giao dịch",
} as const;

export const CONNECTION_LABELS = {
  CONNECTED: "MT5 đã kết nối",
  RECONNECTING: "Đang kết nối lại",
  DISCONNECTED: "MT5 mất kết nối",
} as const;

export const QUOTE_FRESHNESS_LABELS = {
  LIVE: "Dữ liệu live",
  STALE: "Dữ liệu cũ",
  UNAVAILABLE: "Không khả dụng",
} as const;

export const DIRECTION_LABELS = {
  BUY: "Mua",
  SELL: "Bán",
  HOLD: "Giữ",
  NO_SIGNAL: "Không có tín hiệu",
  INVALID: "Không hợp lệ",
  LONG: "Long",
  SHORT: "Short",
  FLAT: "Không giao dịch",
} as const;

export const PNL_LABELS = {
  profit: "Lãi",
  loss: "Lỗ",
  flat: "Hòa vốn",
} as const;

export const EXIT_REASON_LABELS = {
  stop_loss: "Cắt lỗ (SL)",
  take_profit: "Chốt lời (TP)",
  end_of_data: "Hết dữ liệu",
  manual: "Thủ công",
} as const;

export const RISK_LEVEL_LABELS = {
  normal: "Bình thường",
  warning: "Cảnh báo",
  critical: "Nguy hiểm",
} as const;

export const RISK_GROUP_LABELS = {
  account: "Rủi ro tài khoản",
  trade: "Rủi ro giao dịch",
  daily: "Rủi ro trong ngày",
  drawdown: "Rủi ro Drawdown",
  exposure: "Mức phơi nhiễm",
} as const;

export const BACKTEST_STATUS_LABELS = {
  completed: "Hoàn tất",
  insufficient_data: "Dữ liệu chưa đủ",
  data_validation_failed: "Xác thực dữ liệu thất bại",
} as const;

export const QUALITY_STATUS_LABELS = {
  VALID: "HỢP LỆ",
  WARNING: "CẢNH BÁO",
  INSUFFICIENT: "CHƯA ĐỦ",
} as const;

export const METRICS = {
  balance: "Số dư",
  equity: "Vốn chủ sở hữu",
  todayPnl: "PnL hôm nay",
  totalPnl: "Tổng PnL",
  drawdown: "Drawdown",
  margin: "Ký quỹ",
  freeMargin: "Ký quỹ khả dụng",
  unrealizedPnl: "PnL chưa thực hiện",
  botStatus: "Trạng thái Bot",
  connectionStatus: "Trạng thái kết nối",
  openPositions: "Vị thế đang mở",
  liveQuotes: "Giá thị trường",
  recentTrades: "Giao dịch gần đây",
  currentSignal: "Tín hiệu hiện tại",
  netProfit: "Lợi nhuận ròng",
  returnPct: "Lợi suất",
  profitFactor: "Hệ số lợi nhuận",
  maxDrawdown: "Drawdown tối đa",
  winRate: "Tỷ lệ thắng",
  expectancy: "Kỳ vọng lợi nhuận",
  totalTrades: "Tổng giao dịch",
  avgWinLoss: "TB thắng / thua",
  grossProfit: "Lợi nhuận gộp",
  grossLoss: "Khoản lỗ gộp",
  grossPnl: "PnL gộp",
  commission: "Phí hoa hồng",
  swap: "Phí qua đêm",
  riskPerTrade: "Rủi ro mỗi giao dịch",
  accountEquity: "Vốn tài khoản",
  floatingPnl: "PnL thả nổi",
  leverage: "Đòn bẩy",
  marginLevel: "Mức ký quỹ",
} as const;

export const A11Y = {
  mainNav: "Điều hướng chính",
  mobileNav: "Điều hướng di động",
  closeNav: "Đóng menu điều hướng",
  openNav: "Mở menu điều hướng",
  closeMenu: "Đóng menu",
  tradeFilters: "Bộ lọc giao dịch",
  backtestRuns: "Danh sách Backtest",
  performanceSummary: "Tổng quan hiệu suất",
  drawdownAnalysis: "Phân tích Drawdown",
  historicalSimulation: "Dữ liệu mô phỏng lịch sử",
  equityChart: "Biểu đồ vốn theo thời gian",
  drawdownChart: "Biểu đồ Drawdown theo thời gian",
  monthlyPnlChart: "Biểu đồ PnL theo tháng",
  rDistributionChart: "Biểu đồ phân phối hệ số R",
  liveQuotes: "Bảng giá thị trường realtime",
  quoteFreshness: "Độ tươi của giá thị trường",
  accountSwitch: "Chuyển tài khoản demo hoặc thật",
  closeAccountConfirm: "Đóng hộp thoại xác nhận chuyển tài khoản",
  liveCandleEngine: "Trạng thái Live Candle Engine",
  researchSignalEngine: "Trạng thái Signal Engine nghiên cứu",
  paperTrading: "Paper Trading — khớp lệnh ảo, không phải vị thế Exness",
} as const;

export const CANDLE_ENGINE = {
  label: "Live Candle Engine",
  lastClosed: "Nến đóng gần nhất",
  dataSource: "Nguồn dữ liệu",
  none: "Chưa có nến đóng",
} as const;

export const SIGNAL_ENGINE = {
  label: "Signal Engine",
  researchBadge: "TÍN HIỆU NGHIÊN CỨU — KHÔNG PHẢI LỆNH",
  lastSignal: "Tín hiệu gần nhất",
  lastCandle: "Nến đóng gần nhất",
  none: "Chưa có tín hiệu",
  strategy: "Chiến lược",
} as const;

export const PAPER_TRADING = {
  title: "PAPER TRADING",
  mode: "PAPER ONLY",
  researchBadge: "PAPER / RESEARCH — KHÔNG PHẢI VỊ THẾ EXNESS",
  warning: "PAPER ONLY — KHÔNG PHẢI VỊ THẾ THẬT TRÊN EXNESS",
  banner:
    "Đây là khớp lệnh ảo trên tài khoản giấy $10,000. Không có lệnh nào được gửi tới Exness.",
  paperAccount: "Tài khoản giấy (PAPER ACCOUNT)",
  brokerAccount: "Tài khoản broker Exness — xem ở Tổng quan / Vị thế",
  brokerAccountTitle: "Tài khoản broker (BROKER ACCOUNT)",
  paperPosition: "PAPER POSITION",
  lastExecution: "Khớp lệnh gần nhất",
  lastSignal: "Tín hiệu gần nhất",
  openPositions: "Vị thế giấy đang mở",
  session: "Phiên paper",
  none: "Chưa có",
  tableTitle: "Nhật ký paper",
  status: "Trạng thái",
  reason: "Lý do",
  emptyTitle: "Chưa có giao dịch giấy",
  emptyDescription:
    "Khi Signal Engine phát tín hiệu BUY/SELL actionable, Paper Executor sẽ mô phỏng khớp lệnh tại đây.",
} as const;

export const PAPER_STATUS_LABELS = {
  OPEN: "Đang mở",
  CLOSED: "Đã đóng",
  REJECTED: "Từ chối",
  FILLED: "Đã khớp ảo",
  IGNORED: "Bỏ qua",
  DUPLICATE: "Trùng",
} as const;

export const PAPER_REASON_LABELS = {
  SL: "Cắt lỗ (SL)",
  TP: "Chốt lời (TP)",
  MANUAL: "Thủ công",
  END_OF_SESSION: "Hết phiên",
  RISK_LIMIT: "Giới hạn rủi ro",
  MAX_DAILY_LOSS: "Lỗ tối đa trong ngày",
  MAX_DRAWDOWN: "Drawdown tối đa",
  MAX_OPEN_POSITIONS: "Số vị thế mở tối đa",
  POSITION_SIZE_LIMIT: "Giới hạn khối lượng",
  INVALID_RISK: "Rủi ro không hợp lệ",
  INVALID_SL: "SL không hợp lệ",
} as const;

export const formatExitReason = (reason: keyof typeof EXIT_REASON_LABELS): string =>
  EXIT_REASON_LABELS[reason] ?? reason;
