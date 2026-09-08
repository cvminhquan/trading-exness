import { describe, expect, it } from "vitest";
import { executionCandidateStatusSchema } from "@/domain/schemas";
import { mockExecutionCandidateStatus } from "@/mocks/data";

describe("executionCandidateStatusSchema", () => {
  it("parses mock blocked waiting status", () => {
    const parsed = executionCandidateStatusSchema.parse(mockExecutionCandidateStatus);
    expect(parsed.eligible).toBe(false);
    expect(parsed.setupState).toBe("WAITING_FOR_ENTRY");
    expect(parsed.candidate).toBeNull();
    expect(parsed.strategyId).toBe("mtf_technical_v1");
    expect(parsed.confidenceMeaning).toBe("EVIDENCE_ALIGNMENT");
  });
});
