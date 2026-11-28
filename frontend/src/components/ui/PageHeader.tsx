import type { ReactNode } from "react";

/** Page title with an icon tile, an optional subtitle and actions — the same heading treatment on every screen. */
export function PageHeader({ icon, title, subtitle, children, id }: {
  icon?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Badges or actions shown under the title. */
  children?: ReactNode;
  id?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-3">
        {icon && <span className="mt-1 grid size-11 shrink-0 place-items-center rounded-xl bg-primary-soft text-primary">{icon}</span>}
        <div className="min-w-0 space-y-1">
          <h1 id={id} className="text-2xl font-bold text-ink sm:text-3xl">{title}</h1>
          {subtitle && <p className="text-muted">{subtitle}</p>}
        </div>
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

/** A white card section with a heading (dashboards, booking, quotes). */
export function Card({ id, title, icon, action, children, className = "" }: {
  id?: string;
  title: ReactNode;
  icon?: ReactNode;
  /** A link or button shown at the end of the heading row. */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section id={id} aria-labelledby={headingId} className={`card scroll-mt-28 space-y-3 p-4 sm:p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={headingId} className="flex items-center gap-2 text-lg font-bold">
          {icon && <span className="text-primary">{icon}</span>}
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}
