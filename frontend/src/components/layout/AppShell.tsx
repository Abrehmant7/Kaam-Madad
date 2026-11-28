import { HardHat, House, LogIn, LogOut, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";

import type { AccountUser } from "../../api/auth";
import { useAuth } from "../../auth/context";
import { homePathFor, PATHS } from "../../auth/paths";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { Ltr } from "../Ltr";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { LogoMark } from "../icons";
import { clearDrafts } from "../../features/drafts";
import { isActive, navigationFor, type NavItem } from "./navigation";

/** True while a text field has focus: on phones the on-screen keyboard is open, so the bottom bar steps aside and
 * never covers the field or the button under it. */
function useTyping(): boolean {
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    const editable = (node: EventTarget | null) =>
      node instanceof HTMLElement && (node.isContentEditable || node.tagName === "TEXTAREA" ||
        (node.tagName === "INPUT" && !["button", "checkbox", "radio", "submit", "file", "range", "color"].includes((node as HTMLInputElement).type)));
    const onIn = (event: FocusEvent) => setTyping(editable(event.target));
    const onOut = (event: FocusEvent) => setTyping(editable(event.relatedTarget));
    document.addEventListener("focusin", onIn);
    document.addEventListener("focusout", onOut);
    return () => { document.removeEventListener("focusin", onIn); document.removeEventListener("focusout", onOut); };
  }, []);
  return typing;
}

/** Dashboard section links (`/worker#bookings`): scroll to the section once it has loaded. */
function useSectionScroll() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    let tries = 0;
    const timer = window.setInterval(() => {
      const target = document.getElementById(hash.slice(1));
      tries += 1;
      if (target) {
        target.scrollIntoView({ block: "start", behavior: "smooth" });
        window.clearInterval(timer);
      } else if (tries > 40) {
        window.clearInterval(timer);
      }
    }, 75);
    return () => window.clearInterval(timer);
  }, [pathname, hash]);
}

function Brand({ to, compact = false }: { to: string; compact?: boolean }) {
  const { t } = useI18n();
  return (
    <Link to={to} className="flex min-h-11 min-w-0 items-center gap-2.5 rounded-xl px-1" aria-label={t("nav.home")}>
      <LogoMark className={compact ? "size-9 shrink-0" : "size-11 shrink-0"} />
      <span className="min-w-0 leading-tight">
        <span className="font-display block truncate text-lg text-ink">{t("app.name")}</span>
        {!compact && <span className="block font-sans text-[11px] font-semibold tracking-[0.11em] text-muted uppercase" lang="en">Kaam Madad</span>}
      </span>
    </Link>
  );
}

function SideLink({ item }: { item: NavItem }) {
  const { t } = useI18n();
  const { pathname, hash } = useLocation();
  const active = isActive(item, pathname, hash);
  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      className={`relative flex min-h-12 items-center gap-3 rounded-xl px-3 font-bold transition-colors ${
        active ? "bg-primary-soft text-primary before:absolute before:inset-y-3 before:start-0 before:w-[3px] before:rounded before:bg-primary" : "text-[#495873] hover:bg-[#f4f6fb] hover:text-primary"
      }`}
    >
      {item.icon}
      <span>{t(item.label)}</span>
    </Link>
  );
}

function RoleLabel({ user }: { user: AccountUser }) {
  const { t } = useI18n();
  if (user.role === "worker") return <>{t("role.worker.badge")}</>;
  if (user.role === "customer") return <>{t("role.customer.badge")}</>;
  return <>{t("nav.home")}</>;
}

/**
 * Page frame. Signed-in users get a role-aware sidebar on desktop and a bottom bar with the four most useful
 * destinations on phones; the language switch stays in the top bar on every screen. Every page gets the full width
 * beside the sidebar: pages keep prose and input groups to comfortable line lengths themselves. Logical (start/end)
 * spacing works in RTL and LTR.
 */
export function AppShell() {
  const { t } = useI18n();
  const { state, user, logout, retry } = useAuth();
  const { pathname, hash } = useLocation();
  const typing = useTyping();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);
  useSectionScroll();

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      // Protected pages redirect to the landing page themselves once logged out;
      // public pages (e.g. the catalog) simply stay where they are.
      await logout();
      clearDrafts();
    } catch (error) {
      setLogoutError(error);
    } finally {
      setLoggingOut(false);
    }
  }

  const nav = user ? navigationFor(user) : null;
  const home = user ? homePathFor(user) : PATHS.landing;
  const withBar = Boolean(nav && nav.quick.length);

  const logoutButton = (extra = "") => (
    <button
      type="button"
      onClick={() => void handleLogout()}
      disabled={loggingOut}
      className={`flex min-h-11 items-center gap-1.5 rounded-xl px-2.5 text-sm font-bold text-[#495873] hover:bg-[#f4f6fb] hover:text-primary disabled:opacity-60 ${extra}`}
    >
      <LogOut className="size-5 shrink-0 rtl:-scale-x-100" aria-hidden />
      <span>{t("nav.logout")}</span>
    </button>
  );

  return (
    <div className="min-h-dvh bg-surface text-ink">
      <a href="#main-content" className="skip-link">
        {t("nav.skipToContent")}
      </a>

      {user && nav && (
        <aside className="fixed inset-y-0 start-0 z-40 hidden w-64 flex-col overflow-y-auto border-e border-line bg-white px-4 pt-6 pb-4 lg:flex">
          <Brand to={home} />
          <p className="mx-3 mt-7 mb-2 text-sm font-bold text-muted">
            {user.role === "worker" ? t("nav.workspace.worker") : user.role === "customer" ? t("nav.workspace.customer") : t("nav.home")}
          </p>
          <nav aria-label={t("nav.mainMenu")} className="grid gap-1">
            {nav.main.map((item) => (
              <SideLink key={item.to} item={item} />
            ))}
          </nav>
          <p className="mx-3 mt-6 mb-2 text-sm font-bold text-muted">{t("nav.account")}</p>
          <nav aria-label={t("nav.account")} className="grid gap-1">
            {nav.account.map((item) => (
              <SideLink key={item.to} item={item} />
            ))}
          </nav>
          <div className="mt-auto pt-6">
            <div className="flex items-center gap-3 border-t border-line px-1 pt-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary-soft text-primary">
                {user.role === "worker" ? <HardHat className="size-5" aria-hidden /> : user.role === "customer" ? <House className="size-5" aria-hidden /> : <ShieldCheck className="size-5" aria-hidden />}
              </span>
              <div className="min-w-0 text-sm">
                <p className="font-bold"><RoleLabel user={user} /></p>
                <Ltr className="text-muted">{user.phone_number_masked}</Ltr>
              </div>
            </div>
          </div>
        </aside>
      )}

      <div className={user && nav ? "lg:ps-64" : ""}>
        <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/85">
          <div className="flex w-full items-center justify-between gap-2 px-3 py-2 sm:px-6 lg:px-8">
            <div className={user && nav ? "lg:hidden" : ""}>
              <Brand to={home} compact />
            </div>
            {user && nav && (
              <p className="hidden items-center gap-2 font-bold lg:flex">
                <span className="grid size-8 place-items-center rounded-lg bg-primary-soft text-primary">
                  {user.role === "worker" ? <HardHat className="size-5" aria-hidden /> : <House className="size-5" aria-hidden />}
                </span>
                {user.role === "worker" ? t("nav.workspace.worker") : user.role === "customer" ? t("nav.workspace.customer") : t("app.name")}
              </p>
            )}
            <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
              <LanguageSwitch />
              {user ? (
                logoutButton()
              ) : (
                pathname !== PATHS.login && (
                  <Link to={PATHS.login} className="hidden min-h-11 items-center gap-1.5 rounded-xl px-3 text-sm font-bold text-primary hover:bg-primary-soft sm:flex">
                    <LogIn className="size-5 rtl:-scale-x-100" aria-hidden />
                    {t("landing.login")}
                  </Link>
                )
              )}
            </div>
          </div>
        </header>

        <main
          id="main-content"
          tabIndex={-1}
          className={`w-full space-y-4 px-4 pt-5 outline-none sm:px-6 lg:px-8 lg:pt-6 ${withBar ? "pb-28 lg:pb-12" : "pb-12"}`}
        >
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

      {user && nav && withBar && !typing && (
        <nav
          aria-label={t("nav.quickMenu")}
          className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white pb-[env(safe-area-inset-bottom)] lg:hidden"
        >
          <ul className="mx-auto grid max-w-lg grid-cols-4 gap-1 px-1.5 py-1">
            {nav.quick.map((item) => {
              const active = isActive(item, pathname, hash);
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-center text-xs leading-tight ${
                      active ? "bg-primary-soft font-bold text-primary" : "text-muted hover:text-primary"
                    }`}
                  >
                    {item.icon}
                    <span>{t(item.label)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}
