import { describe, expect, it } from "vitest";
import { z } from "zod";
import { createDataEnvelopeSchema } from "@/domain/api/envelope";

const payloadSchema = z.object({ ok: z.boolean() });
const envelopeSchema = createDataEnvelopeSchema(payloadSchema);

describe("createDataEnvelopeSchema", () => {
  it("chấp nhận meta omitted", () => {
    const parsed = envelopeSchema.safeParse({ data: { ok: true } });
    expect(parsed.success).toBe(true);
  });

  it("chấp nhận meta null từ FastAPI", () => {
    const parsed = envelopeSchema.safeParse({ data: { ok: true }, meta: null });
    expect(parsed.success).toBe(true);
  });

  it("chấp nhận meta object", () => {
    const parsed = envelopeSchema.safeParse({ data: { ok: true }, meta: { source: "mt5" } });
    expect(parsed.success).toBe(true);
  });
});
