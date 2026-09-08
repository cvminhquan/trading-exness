import { describe, expect, it } from "vitest";
import { estimateRiskSizing } from "@/lib/risk/sizing";

describe("estimateRiskSizing — tài khoản nhỏ", () => {
  it("cho phép 0.01 lot với equity $10.50 và báo thiếu ngân sách theo %", () => {
    const result = estimateRiskSizing({
      equity: 10.5,
      riskPerTradePct: 0.5,
      brokerMinLot: 0.01,
      stopDistancePrice: 5,
      contractSize: 100,
    });

    expect(result).not.toBeNull();
    expect(result?.minLotAllowed).toBe(true);
    expect(result?.brokerMinLot).toBe(0.01);
    expect(result?.riskBudget).toBeCloseTo(0.0525, 6);
    expect(result?.calculatedLot).toBe(0);
    expect(result?.riskAtMinLot).toBeCloseTo(5, 6);
    expect(result?.riskPctAtMinLot).toBeCloseTo((5 / 10.5) * 100, 4);
    expect(result?.shortfall).toBeCloseTo(5 - 0.0525, 6);
    expect(result?.withinConfiguredRisk).toBe(false);
  });

  it("đủ ngân sách khi equity lớn", () => {
    const result = estimateRiskSizing({
      equity: 10_000,
      riskPerTradePct: 0.5,
      brokerMinLot: 0.01,
      stopDistancePrice: 5,
      contractSize: 100,
    });
    expect(result?.minLotAllowed).toBe(true);
    expect(result?.withinConfiguredRisk).toBe(true);
    expect(result?.shortfall).toBe(0);
    expect(result?.calculatedLot).toBeGreaterThanOrEqual(0.01);
  });
});
