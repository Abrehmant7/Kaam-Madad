import { FlaskConical, LogOut } from "lucide-react";
import { useState } from "react";
import { Link, Outlet } from "react-router";

import { useAuth } from "../../auth/context";
import { homePathFor, PATHS } from "../../auth/paths";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { LogoMark } from "../icons";

/**
 * Mobile-first page frame: single column, 16px gutters at 360px width, centred
 * and capped on larger screens. Logical (start/end) spacing works in RTL and LTR.
 */
export function AppShell() {
  const { t } = useI18n();
  const { state, config, user, logout, retry } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      // Protected pages redirect to the landing page themselves once logged out;
      // public pages (e.g. the catalog) simply stay where they are.
      await logout();
    } catch (error) {
      setLogoutError(error);
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-surface text-ink">
      <a href="#main-content" className="skip-link">
        {t("nav.skipToContent")}
      </a>

      <header className="bg-primary text-white shadow-sm">
        <div className="mx-auto flex w-full max-w-lg items-center justify-between gap-2 px-4 py-2">
          <Link
            to={user ? homePathFor(user) : PATHS.landing}
            className="flex min-h-11 min-w-0 items-center gap-2 rounded-lg px-1 text-xl font-bold"
            aria-label={t("nav.home")}
          >
            <LogoMark className="size-9 shrink-0" />
            <span className="truncate">{t("app.name")}</span>
          </Link>
          <div className="flex shrink-0 items-center gap-2">
            <LanguageSwitch />
            {user && (
              <button
                type="button"
                onClick={() => void handleLogout()}
                disabled={loggingOut}
                className="flex min-h-11 items-center gap-1.5 rounded-lg border border-white/40 px-3 text-sm font-bold hover:bg-white/10 disabled:opacity-60"
              >
                <LogOut className="size-5" aria-hidden />
                <span>{t("nav.logout")}</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {config?.deployment_mode === "demo" && (
        <div role="note" className="border-b border-accent bg-accent-soft">
          <p className="mx-auto flex w-full max-w-lg items-center gap-2 px-4 py-2 text-sm font-bold text-warning-strong">
            <FlaskConical className="size-5 shrink-0" aria-hidden />
            <span>{t("demo.banner")}</span>
          </p>
        </div>
      )}

      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-lg flex-1 space-y-4 px-4 py-6 outline-none">
        {logoutError !== null && <Alert tone="danger" title={t("auth.logoutFailed")}>{describeError(logoutError, t)}</Alert>}
        {state.status === "error" && (
          <Alert tone="warning" title={t("auth.checkFailed")}>
            <p>{describeError(state.error, t)}</p>
            <Button variant="ghost" className="min-h-11 px-0" onClick={retry}>
              {t("common.retry")}
            </Button>
          </Alert>
        )}
        <Outlet />
      </main>
    </div>
  );
}
