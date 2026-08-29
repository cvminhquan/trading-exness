import type { Direction } from "@/domain";

/** Tham số truy vấn danh sách giao dịch — dùng cho API contract & query keys. */
export type TradeListParams = {
  page?: number;
  pageSize?: number;
  symbol?: string;
  direction?: Direction;
  strategy?: string;
  result?: "WIN" | "LOSS";
  start?: string;
  end?: string;
};

/** Tham số truy vấn danh sách backtest. */
export type BacktestListParams = {
  page?: number;
  pageSize?: number;
  strategy?: string;
  symbol?: string;
  timeframe?: string;
};

export const buildTradeQueryString = (params?: TradeListParams): string => {
  if (!params) return "";
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined) search.set("pageSize", String(params.pageSize));
  if (params.symbol) search.set("symbol", params.symbol);
  if (params.direction) search.set("direction", params.direction);
  if (params.strategy) search.set("strategy", params.strategy);
  if (params.result) search.set("result", params.result);
  if (params.start) search.set("start", params.start);
  if (params.end) search.set("end", params.end);
  const qs = search.toString();
  return qs ? `?${qs}` : "";
};

export const buildBacktestQueryString = (params?: BacktestListParams): string => {
  if (!params) return "";
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined) search.set("pageSize", String(params.pageSize));
  if (params.strategy) search.set("strategy", params.strategy);
  if (params.symbol) search.set("symbol", params.symbol);
  if (params.timeframe) search.set("timeframe", params.timeframe);
  const qs = search.toString();
  return qs ? `?${qs}` : "";
};
