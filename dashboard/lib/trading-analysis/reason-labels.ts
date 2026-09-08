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
  const byCode = new Map<string, string>();
  const add = (code: string, message?: string) => {
    if (byCode.has(code)) return;
    const mapped = mapReasonCode(code);
    // Prefer Vietnamese map; else human message; never leave bare enum if message exists.
    byCode.set(
      code,
      mapped !== code ? mapped : message && message.trim() ? message : code,
    );
  };

  for (const r of input.analysisReasons) {
    if (!r.passed) add(r.code, r.message);
  }
  for (const w of input.analysisWarnings) {
    if (!w.passed) add(w.code, w.message);
  }
  for (const code of input.eligibilityReasons ?? []) {
    add(code);
  }
  if (byCode.size === 0 && input.finalSignal === "WAIT") {
    add("FINAL_SIGNAL_WAIT");
    if (!input.setupState || input.setupState === "NO_SETUP") {
      add("NO_DIRECTIONAL_SETUP");
    }
  }
  return [...byCode.entries()].map(([code, label]) => ({ code, label }));
};
