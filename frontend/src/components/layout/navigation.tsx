import { CalendarCheck, ClipboardList, Flag, House, Inbox, MessageSquarePlus, Phone, ShieldCheck, UserRound } from "lucide-react";
import type { ReactNode } from "react";

import type { AccountUser } from "../../api/auth";
import { PATHS } from "../../auth/paths";
import type { TranslationKey } from "../../i18n/types";

export interface NavItem {
  /** A real route, or a dashboard section (`/worker#bookings`). */
  to: string;
  label: TranslationKey;
  icon: ReactNode;
}

const icon = (Icon: typeof House) => <Icon className="size-5 shrink-0" aria-hidden />;

/**
 * Role-aware destinations. `main` drives the desktop sidebar; `quick` the mobile bottom bar (four most useful).
 * Access rules stay in the routes (RequireAuth with a role): navigation only offers the user's own areas.
 */
export function navigationFor(user: AccountUser): { main: NavItem[]; quick: NavItem[]; account: NavItem[] } {
  const account: NavItem[] = [
    { to: PATHS.phone, label: "nav.phone", icon: icon(Phone) },
  ];
  if (user.role === "worker") {
    const home: NavItem = { to: PATHS.worker, label: "nav.home", icon: icon(House) };
    const invitations: NavItem = { to: `${PATHS.worker}#invitations`, label: "nav.invitations", icon: icon(Inbox) };
    const bookings: NavItem = { to: `${PATHS.worker}#bookings`, label: "nav.bookings", icon: icon(CalendarCheck) };
    const reports: NavItem = { to: "/reports", label: "nav.reports", icon: icon(Flag) };
    return {
      main: [
        home, invitations, bookings,
        { to: PATHS.workerProfile, label: "nav.profile", icon: icon(UserRound) },
        { to: PATHS.workerVerify, label: "nav.verify", icon: icon(ShieldCheck) },
        reports,
      ],
      quick: [home, invitations, bookings, reports],
      account,
    };
  }
  if (user.role === "customer") {
    const home: NavItem = { to: PATHS.customer, label: "nav.home", icon: icon(House) };
    const create: NavItem = { to: PATHS.newJob, label: "nav.newRequest", icon: icon(MessageSquarePlus) };
    const requests: NavItem = { to: `${PATHS.customer}#requests`, label: "nav.requests", icon: icon(ClipboardList) };
    const bookings: NavItem = { to: `${PATHS.customer}#bookings`, label: "nav.bookings", icon: icon(CalendarCheck) };
    return {
      main: [home, create, requests, bookings, { to: "/reports", label: "nav.reports", icon: icon(Flag) }],
      quick: [home, create, requests, bookings],
      account,
    };
  }
  return { main: [{ to: PATHS.account, label: "nav.home", icon: icon(House) }], quick: [], account };
}

/** Is this item the current place? Section links match their hash; the home link only without a hash. */
export function isActive(item: NavItem, pathname: string, hash: string): boolean {
  const [path, section] = item.to.split("#");
  if (section) return pathname === path && hash === `#${section}`;
  if (path === PATHS.worker || path === PATHS.customer) return pathname === path && !hash;
  return pathname === path || pathname.startsWith(`${path}/`);
}
