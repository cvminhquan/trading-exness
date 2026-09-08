/**
 * Ước lượng rủi ro tài khoản nhỏ (chỉ đọc).
 * Broker min lot (vd. 0.01) vẫn được coi là mở được;
 * so sánh ngân sách theo % cấu hình với rủi ro thực tế nếu bắt buộc lấy min lot.
 */

export type RiskSizingInput = {
  equity: number;
  riskPerTradePct: number;
  brokerMinLot?: number;
  /** Khoảng SL ước lượng (đơn vị giá). */
  stopDistancePrice?: number;
  contractSize?: number;
};

export type RiskSizingResult = {
  riskBudget: number;
  calculatedLot: number;
  brokerMinLot: number;
  /** Luôn true nếu equity > 0 — tài khoản nhỏ vẫn được mở min lot. */
  minLotAllowed: boolean;
  riskAtMinLot: number;
  riskPctAtMinLot: number;
  /** Số tiền thiếu so với rủi ro của 0.01 lot (theo giả định SL). */
  shortfall: number;
  /** true khi ngân sách % đủ để cover rủi ro min lot. */
  withinConfiguredRisk: boolean;
};

export const estimateRiskSizing = ({
  equity,
  riskPerTradePct,
  brokerMinLot = 0.01,
  stopDistancePrice = 5,
  contractSize = 100,
}: RiskSizingInput): RiskSizingResult | null => {
  if (!Number.isFinite(equity) || equity <= 0) return null;
  if (!Number.isFinite(riskPerTradePct) || riskPerTradePct < 0) return null;

  const riskBudget = (equity * riskPerTradePct) / 100;
  const riskPerLot = stopDistancePrice * contractSize;
  const calculatedLot =
    riskPerLot > 0 ? Math.floor((riskBudget / riskPerLot) * 1000) / 1000 : 0;
  const riskAtMinLot = brokerMinLot * riskPerLot;
  const riskPctAtMinLot = (riskAtMinLot / equity) * 100;
  const shortfall = Math.max(0, riskAtMinLot - riskBudget);

  return {
    riskBudget,
    calculatedLot,
    brokerMinLot,
    minLotAllowed: true,
    riskAtMinLot,
    riskPctAtMinLot,
    shortfall,
    withinConfiguredRisk: shortfall <= 1e-9,
  };
};
