import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

/** Soft semantic pills for system state — not interactive buttons. */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-semibold tracking-wide",
  {
    variants: {
      variant: {
        default:
          "border-[var(--border)] bg-[var(--surface-subtle)] text-[var(--foreground-secondary)]",
        success:
          "border-[var(--positive)]/20 bg-[var(--positive-subtle)] text-[var(--positive)]",
        warning:
          "border-[var(--warning)]/25 bg-[var(--warning-subtle)] text-[var(--warning)]",
        danger:
          "border-[var(--negative)]/20 bg-[var(--negative-subtle)] text-[var(--negative)]",
        info: "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

type BadgeProps = HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>;

export const Badge = ({ className, variant, ...props }: BadgeProps) => (
  <span className={cn(badgeVariants({ variant }), className)} {...props} />
);
