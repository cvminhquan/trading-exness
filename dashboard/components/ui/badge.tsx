import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

/** Compact state chips — only for real states, not decorative labels. */
const badgeVariants = cva(
  "inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
  {
    variants: {
      variant: {
        default: "border-slate-200 bg-transparent text-slate-600",
        success: "border-emerald-300 bg-transparent text-emerald-800",
        warning: "border-amber-300 bg-transparent text-amber-800",
        danger: "border-rose-300 bg-transparent text-rose-800",
        info: "border-slate-300 bg-transparent text-slate-700",
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
