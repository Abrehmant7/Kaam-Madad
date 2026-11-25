import { type ReactNode, useRef } from "react";
import { Navigate, Outlet, useLocation } from "react-router";

import type { Role } from "../api/auth";
import { PageLoader } from "../components/ui/PageLoader";
import { useAuth } from "./context";
import { homePathFor, PATHS } from "./paths";

/**
 * Navigation convenience only — the backend enforces every permission.
 * Redirect targets are always the user's own home, so there are no loops.
 */
export function RequireAuth({ role, children }: { role?: Role; children?: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === "loading") return <PageLoader />;
  // The shell shows the failed check with a retry button; render nothing else.
  if (state.status === "error") return null;
  if (state.status === "anonymous") {
    if (state.loggedOut) return <Navigate to={PATHS.landing} replace />;
    const params = new URLSearchParams({ next: location.pathname + location.search });
    if (state.sessionExpired) params.set("expired", "1");
    return <Navigate to={`${PATHS.login}?${params.toString()}`} replace />;
  }
  if (role && state.user.role !== role) return <Navigate to={homePathFor(state.user)} replace />;
  return <>{children ?? <Outlet />}</>;
}

/**
 * Pages for signed-out visitors (landing, start, signup, login). Users who were
 * already signed in when they arrived go to their home. Users who sign in ON
 * these pages are left alone, so the form can navigate (e.g. signup → phone
 * confirmation, login → ?next=) without this guard racing it.
 */
export function GuestOnly({ children }: { children?: ReactNode }) {
  const { state } = useAuth();
  const arrival = useRef<"guest" | "member" | null>(null);
  if (arrival.current === null && state.status !== "loading") {
    arrival.current = state.status === "authenticated" ? "member" : "guest";
  }

  if (state.status === "loading") return <PageLoader />;
  if (state.status === "authenticated" && arrival.current === "member") {
    return <Navigate to={homePathFor(state.user)} replace />;
  }
  // "error": still show the page; the shell explains the failed check and offers a retry.
  return <>{children ?? <Outlet />}</>;
}
