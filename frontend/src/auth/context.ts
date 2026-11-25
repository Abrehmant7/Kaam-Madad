import { createContext, useContext } from "react";

import type { AccountUser, ClientConfig, SignupPayload } from "../api/auth";

export type AuthState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  /** sessionExpired: the server dropped the session. loggedOut: the user chose to log out. */
  | { status: "anonymous"; sessionExpired: boolean; loggedOut?: boolean }
  | { status: "authenticated"; user: AccountUser };

export interface AuthContextValue {
  state: AuthState;
  /** Server configuration (demo mode, phone provider); null until loaded. */
  config: ClientConfig | null;
  user: AccountUser | null;
  retry: () => void;
  login: (phoneNumber: string, password: string) => Promise<AccountUser>;
  signup: (payload: SignupPayload) => Promise<AccountUser>;
  logout: () => Promise<void>;
  /** Replace the user after a successful mutation that returned it. */
  setUser: (user: AccountUser) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>.");
  return value;
}
