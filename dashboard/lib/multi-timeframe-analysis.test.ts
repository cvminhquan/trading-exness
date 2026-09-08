import { describe, expect, it } from "vitest";
import { multiTimeframeAnalysisSchema } from "@/domain/schemas";
import { mockMultiTimeframeAnalysis } from "@/mocks/data";

describe("multiTimeframeAnalysisSchema", () => {
  it("parses mock multi-timeframe analysis", () => {
    const parsed = multiTimeframeAnalysisSchema.parse(mockMultiTimeframeAnalysis);
    expect(parsed.symbol).toBe("XAUUSD");
    expect(parsed.confidenceMeaning).toBe("EVIDENCE_ALIGNMENT");
    expect(parsed.finalSignal).toBe("LONG");
    expect(parsed.timeframes.M15?.signal).toBe("LONG");
    expect(parsed.setup?.state).toBe("WAITING_FOR_ENTRY");
  });

  it("requires confidenceMeaning EVIDENCE_ALIGNMENT", () => {
    expect(() =>
      multiTimeframeAnalysisSchema.parse({
        ...mockMultiTimeframeAnalysis,
        confidenceMeaning: "WIN_PROBABILITY",
      }),
    ).toThrow();
  });

  it("exposes brokerExecutable vs riskAcceptable on small account", () => {
    const parsed = multiTimeframeAnalysisSchema.parse(mockMultiTimeframeAnalysis);
    expect(parsed.sizing?.brokerExecutable).toBe(true);
    expect(parsed.sizing?.riskAcceptable).toBe(false);
  });
});
