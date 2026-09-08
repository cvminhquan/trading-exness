import { cn } from "@/lib/utils";

type MiniSparklineProps = {
  values: number[];
  className?: string;
  /** positive → emerald; negative → rose; flat → muted */
  tone?: "up" | "down" | "flat";
  label?: string;
  /** Unique id suffix so multiple sparklines không đụng gradient SVG. */
  gradientKey?: string;
};

/** SVG sparkline từ chuỗi số thật — cần ≥ 2 điểm. */
export const MiniSparkline = ({
  values,
  className,
  tone = "flat",
  label = "Biến động giá trong phiên Dashboard",
  gradientKey = "default",
}: MiniSparklineProps) => {
  if (values.length < 2) return null;

  const width = 72;
  const height = 28;
  const padY = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const gradientId = `spark-fill-${gradientKey}-${tone}`;

  const coords = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - padY - ((v - min) / span) * (height - padY * 2);
    return { x, y };
  });

  const linePoints = coords.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
  const areaPath = [
    `M ${coords[0]!.x.toFixed(2)} ${height}`,
    ...coords.map((p) => `L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`),
    `L ${coords[coords.length - 1]!.x.toFixed(2)} ${height}`,
    "Z",
  ].join(" ");

  const stroke =
    tone === "up"
      ? "var(--positive)"
      : tone === "down"
        ? "var(--negative)"
        : "var(--muted)";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("shrink-0 overflow-visible", className)}
      aria-label={label}
      role="img"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={linePoints}
      />
    </svg>
  );
};
