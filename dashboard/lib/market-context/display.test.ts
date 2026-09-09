import { describe, expect, it } from "vitest";
import { marketSynthesisSchema } from "@/domain/schemas";
import { mockMarketSynthesis } from "@/mocks/data";
import {
  alignmentLabel,
  biasLabel,
  safeExternalHref,
  stateLabel,
  statusLabel,
} from "@/lib/market-context/display";

describe("marketSynthesisSchema", () => {
  it("parses mock conflict scenario without mutating directions", () => {
    expect(mockMarketSynthesis.technicalView.primaryBias).toBe("BEARISH");
    expect(mockMarketSynthesis.externalView.externalBias).toBe(
      "BULLISH_FOR_GOLD",
    );
    expect(mockMarketSynthesis.externalView.alignmentWithTechnical).toBe(
      "CONFLICT",
    );
    expect(mockMarketSynthesis.synthesis.state).toBe(
      "TECHNICAL_EXTERNAL_CONFLICT",
    );
    expect(mockMarketSynthesis.technicalView.botSignal).toBe("SHORT");
    expect(mockMarketSynthesis.externalView.eventRisk).toBe("HIGH");
  });

  it("accepts TECHNICAL_ONLY / disabled external gracefully", () => {
    const data = marketSynthesisSchema.parse({
      symbol: "XAUUSD",
      generated_at: "2026-09-09T12:00:00+00:00",
      status: "TECHNICAL_ONLY",
      technical_view: {
        primary_bias: "BULLISH",
        bot_signal: "LONG",
        mtf_alignment: "ALIGNED",
        timeframes: { M15: { trend: "BULLISH" } },
      },
      external_view: {
        status: "DISABLED",
        external_bias: "INSUFFICIENT_EVIDENCE",
        alignment_with_technical: "INSUFFICIENT_DATA",
        event_risk: "UNKNOWN",
        top_drivers: [],
        important_events: [],
        supporting_factors: [],
        conflicting_factors: [],
        source_count: 0,
        freshness: "UNDATED",
      },
      synthesis: {
        state: "TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL",
        summary: "Technical only.",
        technical_explanation: "M15 bullish.",
        external_explanation: "External disabled.",
        alignment_explanation: "No external confirmation.",
        risk_explanation: "Event risk unknown.",
        uncertainties: [],
        what_to_watch: [],
      },
      sources: [],
      ai_metadata: {
        enabled: false,
        used: false,
        fallback_used: true,
      },
    });
    expect(data.status).toBe("TECHNICAL_ONLY");
    expect(data.externalView.status).toBe("DISABLED");
    expect(data.aiMetadata.fallbackUsed).toBe(true);
  });

  it("handles PARTIAL, STALE, UNAVAILABLE, and unknown enums", () => {
    for (const status of ["PARTIAL", "STALE", "UNAVAILABLE", "WEIRD_STATUS"]) {
      const data = marketSynthesisSchema.parse({
        symbol: "XAUUSD",
        status,
        technical_view: { primary_bias: "NEUTRAL", bot_signal: "WAIT" },
        external_view: {
          external_bias: "NOT_A_REAL_BIAS",
          alignment_with_technical: "SUPPORT",
          event_risk: "LOW",
        },
        synthesis: { state: "INSUFFICIENT_CONTEXT", summary: "x" },
        sources: [],
        ai_metadata: { enabled: true, used: false, fallback_used: true },
      });
      expect(data.status).toBe(status);
      expect(data.externalView.externalBias).toBe("NOT_A_REAL_BIAS");
    }
  });

  it("keeps AI fallback metadata when AI disabled", () => {
    const data = marketSynthesisSchema.parse({
      symbol: "XAUUSD",
      status: "AVAILABLE",
      technical_view: { primary_bias: "BEARISH", bot_signal: "SHORT" },
      external_view: {
        external_bias: "BEARISH_FOR_GOLD",
        alignment_with_technical: "SUPPORT",
        event_risk: "LOW",
      },
      synthesis: {
        state: "TECHNICAL_EXTERNAL_ALIGNED",
        summary: "Aligned.",
      },
      sources: [],
      ai_metadata: {
        enabled: false,
        used: false,
        fallback_used: true,
        provider: "deterministic",
      },
    });
    expect(data.aiMetadata.enabled).toBe(false);
    expect(data.aiMetadata.used).toBe(false);
    expect(data.aiMetadata.fallbackUsed).toBe(true);
  });

  it("maps source refs and rejects orphan empty source ids gracefully", () => {
    const data = marketSynthesisSchema.parse({
      symbol: "XAUUSD",
      status: "AVAILABLE",
      technical_view: { primary_bias: "BEARISH" },
      external_view: {
        external_bias: "BULLISH_FOR_GOLD",
        alignment_with_technical: "CONFLICT",
        event_risk: "HIGH",
        top_drivers: [
          {
            driver: "USD",
            direction_for_gold: "BEARISH",
            summary: "USD firm",
            evidence_strength: "MODERATE",
            source_ids: ["src_1"],
          },
        ],
      },
      synthesis: { state: "HIGH_EVENT_RISK", summary: "High event risk." },
      sources: [
        {
          source_id: "src_1",
          title: "Reuters",
          domain: "reuters.com",
          url: "https://www.reuters.com/example",
        },
      ],
      ai_metadata: { used: true, fallback_used: false, enabled: true },
    });
    expect(data.sources[0]?.sourceId).toBe("src_1");
    expect(data.externalView.topDrivers[0]?.sourceIds).toEqual(["src_1"]);
    expect(data.synthesis.state).toBe("HIGH_EVENT_RISK");
  });
});

describe("market-context display helpers", () => {
  it("maps enums to Vietnamese labels with graceful unknown fallback", () => {
    expect(statusLabel("AVAILABLE")).toBe("Khả dụng");
    expect(statusLabel("TECHNICAL_ONLY")).toBe("Chỉ kỹ thuật");
    expect(stateLabel("TECHNICAL_EXTERNAL_CONFLICT")).toContain("xung đột");
    expect(biasLabel("BEARISH")).toBe("Giảm");
    expect(biasLabel("BULLISH_FOR_GOLD")).toBe("Tăng cho vàng");
    expect(alignmentLabel("CONFLICT")).toBe("Xung đột");
    expect(statusLabel("TOTALLY_NEW")).toBe("TOTALLY NEW");
  });

  it("only allows http(s) source hrefs", () => {
    expect(safeExternalHref("https://reuters.com/a")).toContain("https://");
    expect(safeExternalHref("http://example.com")).toContain("http://");
    expect(safeExternalHref("javascript:alert(1)")).toBeNull();
    expect(safeExternalHref("file:///etc/passwd")).toBeNull();
    expect(safeExternalHref("")).toBeNull();
    expect(safeExternalHref("not a url")).toBeNull();
  });

  it("preserves conflict comparison semantics for UI copy", () => {
    expect(biasLabel(mockMarketSynthesis.technicalView.primaryBias)).toBe(
      "Giảm",
    );
    expect(biasLabel(mockMarketSynthesis.externalView.externalBias)).toBe(
      "Tăng cho vàng",
    );
    expect(
      alignmentLabel(mockMarketSynthesis.externalView.alignmentWithTechnical),
    ).toBe("Xung đột");
  });
});
