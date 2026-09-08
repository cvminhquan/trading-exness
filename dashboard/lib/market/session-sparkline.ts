/** Ring buffer mid prices per symbol — dữ liệu thật từ quote poll, không fake. */

const MAX_POINTS = 32;
const sessionSeries = new Map<string, number[]>();

export const recordSessionMid = (symbol: string, mid: number): number[] => {
  const prev = sessionSeries.get(symbol) ?? [];
  // Mỗi lần poll ghi 1 điểm (kể cả mid trùng) → sparkline hiện sau ~2 tick
  const next = [...prev, mid];
  const clipped = next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
  sessionSeries.set(symbol, clipped);
  return clipped;
};

export const getSessionMidSeries = (symbol: string): number[] =>
  sessionSeries.get(symbol) ?? [];

export const clearSessionMidSeries = (): void => {
  sessionSeries.clear();
};
