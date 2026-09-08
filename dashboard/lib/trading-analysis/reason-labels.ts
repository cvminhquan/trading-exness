import { ANALYSIS_REASON_LABELS } from "@/lib/i18n/vi";

export type ReasonItem = {
  code: string;
  label: string;
};

export const mapReasonCode = (code: string): string =>
  ANALYSIS_REASON_LABELS[code] ?? code;

export const collectDecisionReasons = (input: {
  analysisReasons: Array<{ code: string; passed: boolean; message: string }>;
  analysisWarnings: Array<{ code: string; passed: boolean; message: string }>;
  eligibilityReasons?: string[];
  finalSignal?: "LONG" | "SHORT" | "WAIT";
  setupState?: string | null;
}): ReasonItem[] => {
  const codes: string[] = [];
  for (const r of input.analysisReasons) {
    if (!r.passed) codes.push(r.code);
  }
  for (const w of input.analysisWarnings) {
    if (!w.passed) codes.push(w.code);
  }
  for (const code of input.eligibilityReasons ?? []) {
    codes.push(code);
  }
  // Fallback presentation khi API chỉ trả TF_* passed=true nhưng đang WAIT.
  if (codes.length === 0 && input.finalSignal === "WAIT") {
    codes.push("FINAL_SIGNAL_WAIT");
    if (!input.setupState || input.setupState === "NO_SETUP") {
      codes.push("NO_DIRECTIONAL_SETUP");
    }
  }
  const unique = [...new Set(codes)];
  return unique.map((code) => ({ code, label: mapReasonCode(code) }));
};
