import { CircleAlert, CircleCheck, Clock, FlaskConical, Info } from "lucide-react";
import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

const TONES: Record<BadgeTone, { classes: string; icon: ReactNode }> = {
  neutral: { classes: "border-line bg-white text-ink", icon: <Clock className="size-4" aria-hidden /> },
  success: { classes: "border-success/40 bg-success-soft text-success-strong", icon: <CircleCheck className="size-4" aria-hidden /> },
  warning: { classes: "border-warning/50 bg-warning-soft text-warning-strong", icon: <FlaskConical className="size-4" aria-hidden /> },
  danger: { classes: "border-danger/40 bg-danger-soft text-danger-strong", icon: <CircleAlert className="size-4" aria-hidden /> },
  info: { classes: "border-primary/30 bg-primary/10 text-primary-strong", icon: <Info className="size-4" aria-hidden /> },
};

/** Small status pill: icon + text (colour is never the only signal). */
export function StatusBadge({ tone = "neutral", icon, children }: { tone?: BadgeTone; icon?: ReactNode; children: ReactNode }) {
  const style = TONES[tone];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-bold ${style.classes}`}>
      {icon ?? style.icon}
      <span>{children}</span>
    </span>
  );
}
