import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import * as authApi from "../api/auth";
import { refreshCsrfToken, setUnauthorizedHandler } from "../api/client";
import { useI18n } from "../i18n/context";
import { AuthContext, type AuthContextValue, type AuthState } from "./context";

/**
 * Session state for the whole app.
 *
 * Start-up: fetch the CSRF cookie, server config and /auth/me/ together. A
 * network failure gives an "error" state with retry — never an endless spinner.
 *
 * Language rule: after login or session restore, the account's stored
 * preference is applied to the UI (and remembered on this device). Anonymous
 * visitors keep the device's choice; signup sends the currently shown language.
 *
 * Any later 401 while signed in means the session ended (expired, logged out
 * elsewhere, or account suspended) → state becomes anonymous with sessionExpired.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const { setLanguage } = useI18n();
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [config, setConfig] = useState<authApi.ClientConfig | null>(null);
  const [attempt, setAttempt] = useState(0);

  // setLanguage is stable (memoised in I18nProvider).
  const applyUser = useCallback(
    (user: authApi.AccountUser) => {
      setState({ status: "authenticated", user });
      setLanguage(user.preferred_language);
    },
    [setLanguage],
  );

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      refreshCsrfToken(controller.signal),
      authApi.fetchConfig(controller.signal),
      authApi.fetchMe(controller.signal),
    ])
      .then(([, loadedConfig, session]) => {
        if (controller.signal.aborted) return;
        setConfig(loadedConfig);
        if (session.authenticated && session.user) {
          applyUser(session.user);
        } else {
          setState({ status: "anonymous", sessionExpired: false });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", error });
      });
    return () => controller.abort();
  }, [attempt, applyUser]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setState((previous) =>
        previous.status === "authenticated" ? { status: "anonymous", sessionExpired: true } : previous,
      );
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  const login = useCallback(
    async (phoneNumber: string, password: string) => {
      const session = await authApi.login(phoneNumber, password);
      if (!session.user) throw new Error("Login response without user");
      applyUser(session.user);
      return session.user;
    },
    [applyUser],
  );

  const signup = useCallback(
    async (payload: authApi.SignupPayload) => {
      const session = await authApi.signup(payload);
      if (!session.user) throw new Error("Signup response without user");
      applyUser(session.user);
      return session.user;
    },
    [applyUser],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    // Protected pages react to this by going to the landing page (see RequireAuth).
    setState({ status: "anonymous", sessionExpired: false, loggedOut: true });
  }, []);

  const setUser = useCallback((user: authApi.AccountUser) => setState({ status: "authenticated", user }), []);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      config,
      user: state.status === "authenticated" ? state.user : null,
      retry,
      login,
      signup,
      logout,
      setUser,
    }),
    [state, config, retry, login, signup, logout, setUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
