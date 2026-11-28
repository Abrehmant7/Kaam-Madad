import { CircleAlert, CircleCheck, FlaskConical, Info } from "lucide-react";
import type { ReactNode } from "react";

type Tone = "info" | "success" | "warning" | "danger" | "demo";

const TONES: Record<Tone, { classes: string; icon: ReactNode; role: "status" | "alert" }> = {
  info: { classes: "border-primary/15 bg-primary-soft text-[#233f80]", icon: <Info className="size-6 text-primary" aria-hidden />, role: "status" },
  success: { classes: "border-success/40 bg-success-soft text-success-strong", icon: <CircleCheck className="size-6" aria-hidden />, role: "status" },
  warning: { classes: "border-warning/50 bg-warning-soft text-warning-strong", icon: <CircleAlert className="size-6" aria-hidden />, role: "status" },
  danger: { classes: "border-danger/40 bg-danger-soft text-danger-strong", icon: <CircleAlert className="size-6" aria-hidden />, role: "alert" },
  demo: { classes: "border-accent/70 bg-accent-soft text-ink", icon: <FlaskConical className="size-6 text-warning-strong" aria-hidden />, role: "status" },
};

/** Message box with icon and optional title. Danger alerts are announced immediately. */
export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: ReactNode; children?: ReactNode }) {
  const style = TONES[tone];
  return (
    <div role={style.role} className={`flex items-start gap-3 rounded-xl border p-3 ${style.classes}`}>
      <span className="mt-1 shrink-0">{style.icon}</span>
      <div className="min-w-0">
        {title && <p className="font-bold">{title}</p>}
        {children && <div>{children}</div>}
      </div>
    </div>
  );
}
