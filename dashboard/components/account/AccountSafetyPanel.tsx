"use client";

import type { AccountSafety } from "@/domain";
import { ACCOUNT_OVERVIEW } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

type AccountSafetyPanelProps = {
  safety: AccountSafety;
};

const Status = ({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}) => (
  <span className="inline-flex items-center gap-1.5 text-[12px]">
    <span
      className={cn(
        "size-1.5 rounded-full",
        tone === "ok" && "bg-[var(--positive)]",
        tone === "warn" && "bg-[var(--warning)]",
        tone === "bad" && "bg-[var(--negative)]",
        tone === "neutral" && "bg-[var(--muted)]",
      )}
      aria-hidden
    />
    <span className="font-medium tracking-wide text-[var(--muted)] uppercase">
      {label}
    </span>
    <span
      className={cn(
        "font-semibold tabular-nums",
        tone === "ok" && "text-[var(--positive)]",
        tone === "warn" && "text-[var(--warning)]",
        tone === "bad" && "text-[var(--negative)]",
        tone === "neutral" && "text-[var(--foreground-secondary)]",
      )}
    >
      {value}
    </span>
  </span>
);

/** Compact status strip under account — not a competing card. */
export const AccountSafetyPanel = ({ safety }: AccountSafetyPanelProps) => (
  <div
    className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 py-1"
    aria-label={ACCOUNT_OVERVIEW.safetyTitle}
    role="status"
  >
    <Status label={ACCOUNT_OVERVIEW.mode} value={safety.tradeMode} />
    <Status
      label={ACCOUNT_OVERVIEW.mt5}
      value={safety.mt5Status}
      tone={safety.mt5Status === "CONNECTED" ? "ok" : "bad"}
    />
    <Status
      label={ACCOUNT_OVERVIEW.executionMode}
      value={safety.executionMode}
      tone={safety.executionMode === "LIVE" ? "warn" : "neutral"}
    />
    <Status
      label={ACCOUNT_OVERVIEW.killSwitch}
      value={safety.killSwitch}
      tone={safety.killSwitch === "ON" ? "ok" : "warn"}
    />
    {safety.server ? (
      <span className="text-[12px] text-[var(--muted)]">{safety.server}</span>
    ) : null}
    <span className="text-[12px] text-[var(--muted)]">Dashboard chỉ đọc</span>
  </div>
);
