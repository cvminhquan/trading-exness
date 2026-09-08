"use client";

import type { AccountSafety } from "@/domain";
import { ACCOUNT_OVERVIEW } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type AccountSafetyPanelProps = {
  safety: AccountSafety;
};

const Chip = ({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}) => (
  <span
    className={cn(
      "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px]",
      tone === "ok" && "border-emerald-200 bg-emerald-50 text-emerald-800",
      tone === "warn" && "border-amber-200 bg-amber-50 text-amber-900",
      tone === "bad" && "border-rose-200 bg-rose-50 text-rose-800",
      tone === "neutral" && "border-slate-200 bg-slate-50 text-slate-700",
    )}
  >
    <span className="font-semibold uppercase tracking-wide opacity-70">
      {label}
    </span>
    <span className="font-semibold tabular-nums">{value}</span>
  </span>
);

/** Compact safety strip — tránh hiểu nhầm bot đang autonomous live trading. */
export const AccountSafetyPanel = ({ safety }: AccountSafetyPanelProps) => (
  <div
    className="flex flex-wrap items-center gap-1.5"
    aria-label={ACCOUNT_OVERVIEW.safetyTitle}
  >
    <Chip label={ACCOUNT_OVERVIEW.mode} value={safety.tradeMode} />
    <Chip
      label={ACCOUNT_OVERVIEW.mt5}
      value={safety.mt5Status}
      tone={safety.mt5Status === "CONNECTED" ? "ok" : "bad"}
    />
    <Chip
      label={ACCOUNT_OVERVIEW.executionMode}
      value={safety.executionMode}
      tone={safety.executionMode === "LIVE" ? "warn" : "neutral"}
    />
    <Chip
      label={ACCOUNT_OVERVIEW.killSwitch}
      value={safety.killSwitch}
      tone={safety.killSwitch === "ON" ? "ok" : "warn"}
    />
    {safety.server ? (
      <span className="text-[11px] text-slate-400">{safety.server}</span>
    ) : null}
    <span className="text-[10px] text-slate-400">
      Dashboard chỉ đọc — không đặt lệnh từ UI
    </span>
  </div>
);
