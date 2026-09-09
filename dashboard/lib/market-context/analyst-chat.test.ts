import { describe, expect, it } from "vitest";
import { marketAnalystChatResponseSchema } from "@/domain/schemas";
import { ANALYST_CHAT } from "@/lib/i18n/vi";
import { safeExternalHref } from "@/lib/market-context/display";

describe("marketAnalystChatResponseSchema", () => {
  it("parses snake_case API payload", () => {
    const data = marketAnalystChatResponseSchema.parse({
      schema_version: "1.0",
      message_id: "m1",
      session_id: "s1",
      symbol: "XAUUSD",
      created_at: "2026-09-09T10:00:00Z",
      answer: "Bot đang WAIT vì M15/H1 bearish.",
      answer_type: "BOT_SIGNAL_EXPLANATION",
      intent: "WHY_BOT_SIGNAL",
      context_status: "AVAILABLE",
      context_changed: true,
      used_context: { technical: true, external: true, synthesis: true },
      technical_fingerprint: "a",
      external_fingerprint: "b",
      synthesis_fingerprint: "c",
      source_refs: ["src_1"],
      sources: [
        {
          source_id: "src_1",
          title: "Reuters",
          domain: "reuters.com",
          url: "https://www.reuters.com/example",
          freshness: "RECENT",
        },
      ],
      warnings: ["ai_chat_disabled", "external_stale"],
      provider_metadata: {
        provider: null,
        model: null,
        used: false,
        fallback_used: true,
        latency_ms: 12,
      },
      chat_enabled: false,
      note: "read-only",
    });

    expect(data.sessionId).toBe("s1");
    expect(data.messageId).toBe("m1");
    expect(data.contextChanged).toBe(true);
    expect(data.chatEnabled).toBe(false);
    expect(data.providerMetadata.fallbackUsed).toBe(true);
    expect(data.sources[0]?.sourceId).toBe("src_1");
    expect(data.usedContext.technical).toBe(true);
  });

  it("rejects unsafe source urls via safeExternalHref helper", () => {
    expect(safeExternalHref("javascript:alert(1)")).toBeNull();
    expect(safeExternalHref("https://reuters.com/a")).toContain("https://");
  });
});

describe("ANALYST_CHAT copy", () => {
  it("has analysis-only suggested questions", () => {
    expect(ANALYST_CHAT.suggested.length).toBeGreaterThan(0);
    for (const q of ANALYST_CHAT.suggested) {
      expect(q.toLowerCase()).not.toContain("buy now");
      expect(q.toLowerCase()).not.toContain("execute");
      expect(q.toLowerCase()).not.toContain("mở lệnh");
    }
    expect(ANALYST_CHAT.disabled).toContain("chưa được bật");
  });
});
