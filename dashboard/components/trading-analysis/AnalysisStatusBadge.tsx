import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "good" | "warn" | "bad";

type AnalysisStatusBadgeProps = {
  label: string;
  tone?: Tone;
  className?: string;
  title?: string;
};

const toneToVariant = {
  neutral: "default",
  good: "success",
  warn: "warning",
  bad: "danger",
} as const;

export const AnalysisStatusBadge = ({
  label,
  tone = "neutral",
  className,
  title,
}: AnalysisStatusBadgeProps) => (
  <Badge
    variant={toneToVariant[tone]}
    className={cn("normal-case tracking-wide", className)}
    title={title}
  >
    {label}
  </Badge>
);
