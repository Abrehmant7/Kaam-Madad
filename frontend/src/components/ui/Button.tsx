import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const BASE =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 py-2 text-base font-bold transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary-strong",
  secondary: "border-2 border-primary bg-white text-primary hover:bg-surface",
  danger: "bg-danger text-white hover:bg-danger-strong",
  ghost: "text-primary underline-offset-4 hover:underline",
};

export function buttonClasses(variant: Variant = "primary", fullWidth = false, extra = ""): string {
  return [BASE, VARIANTS[variant], fullWidth ? "w-full" : "", extra].filter(Boolean).join(" ");
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  /** Icon shown before the label. Every button keeps a visible text label (UX-02). */
  icon?: ReactNode;
  loading?: boolean;
  /** Label shown while loading (e.g. "Logging in…"). */
  loadingLabel?: string;
  fullWidth?: boolean;
}

/** Large (48px) labelled button with optional icon and loading state. */
export function Button({
  variant = "primary",
  icon,
  loading = false,
  loadingLabel,
  fullWidth = false,
  className = "",
  children,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, fullWidth, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <LoaderCircle className="size-5 motion-safe:animate-spin" aria-hidden /> : icon}
      <span>{loading && loadingLabel ? loadingLabel : children}</span>
    </button>
  );
}

interface ButtonLinkProps extends LinkProps {
  variant?: Variant;
  icon?: ReactNode;
  fullWidth?: boolean;
}

/** A router link styled as a large button (navigation, not an action). */
export function ButtonLink({ variant = "primary", icon, fullWidth = false, className = "", children, ...props }: ButtonLinkProps) {
  return (
    <Link className={buttonClasses(variant, fullWidth, className)} {...props}>
      {icon}
      <span>{children}</span>
    </Link>
  );
}
