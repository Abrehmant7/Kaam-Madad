import type { AccountUser } from "../api/auth";

export const PATHS = {
  landing: "/",
  start: "/start",
  signup: "/signup",
  login: "/login",
  phone: "/account/phone",
  account: "/account",
  worker: "/worker",
  workerWork: "/worker/setup/work",
  workerAreas: "/worker/setup/areas",
  workerVerify: "/worker/verify",
  workerProfile: "/worker/profile",
  customer: "/customer",
  newJob: "/customer/requests/new",
  catalog: "/catalog",
  voiceTest: "/voice-test",
} as const;

/** The home screen for a signed-in user, chosen by role. */
export function homePathFor(user: AccountUser): string {
  if (user.role === "worker") return PATHS.worker;
  if (user.role === "customer") return PATHS.customer;
  return PATHS.account;
}

/** Accept only same-site relative paths from ?next= (prevents open redirects). */
export function safeNextPath(raw: string | null): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return null;
  return raw;
}
