import { Link, Outlet } from "react-router";

import { useI18n } from "../../i18n/context";
import { LogoMark } from "../icons";

/**
 * Mobile-first page frame: single column, comfortable 16px gutters at 360px
 * width, centred and capped on larger screens. Uses logical (start/end)
 * spacing so the same markup works in RTL (Urdu) and LTR (English).
 */
export function AppShell() {
  const { t } = useI18n();

  return (
    <div className="flex min-h-dvh flex-col bg-surface text-ink">
      <a href="#main-content" className="skip-link">
        {t("nav.skipToContent")}
      </a>

      <header className="bg-primary text-white shadow-sm">
        <div className="mx-auto flex w-full max-w-lg items-center px-4 py-2">
          <Link
            to="/"
            className="flex min-h-11 items-center gap-3 rounded-lg px-1 text-xl font-bold"
            aria-label={t("nav.home")}
          >
            <LogoMark />
            <span>{t("app.name")}</span>
          </Link>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-lg flex-1 px-4 py-6 outline-none">
        <Outlet />
      </main>
    </div>
  );
}
