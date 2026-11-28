import { ArrowRight, CalendarCheck, CircleCheck, ClipboardList, Inbox, KeyRound, MessageSquarePlus, Power, ShieldCheck, Star, Users } from "lucide-react";
import type { ReactNode } from "react";

import * as bookingsApi from "../../api/bookings";
import * as invitationsApi from "../../api/invitations";
import type { JobListItem } from "../../api/jobs";
import type { WorkerDashboard } from "../../api/workers";
import { PATHS } from "../../auth/paths";
import { ButtonLink } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/types";
import { useLoad } from "../worker/shared";

export interface Step {
  key: string;
  icon: ReactNode;
  to: string;
  action: TranslationKey;
}

const ic = (Icon: typeof Inbox) => <Icon className="size-6" aria-hidden />;
const settle = <T,>(promise: Promise<T>) => promise.catch(() => null);

/** Bookings first (they have a time), then the worker's own setup. Everything comes from the server's state. */
export function workerNextStep(dashboard: WorkerDashboard, bookings: bookingsApi.BookingCard[] | null,
  inbox: invitationsApi.WorkerInvitation[] | null): Step {
  const mine = (bookings ?? []).filter((card) => card.role === "worker");
  const byStatus = (status: bookingsApi.BookingStatus) => mine.find((card) => card.status === status);
  const booking = (card: bookingsApi.BookingCard, key: string, icon: ReactNode): Step =>
    ({ key, icon, to: `/bookings/${card.id}`, action: "next.action.booking" });
  const inProgress = byStatus("in_progress");
  if (inProgress) return booking(inProgress, "worker.finish", ic(CircleCheck));
  const arrived = byStatus("arrived");
  if (arrived) return booking(arrived, "worker.code", ic(KeyRound));
  const confirmed = mine.filter((card) => card.status === "confirmed").sort((a, b) => a.start_at.localeCompare(b.start_at))[0];
  if (confirmed) return booking(confirmed, "worker.arrive", ic(CalendarCheck));
  const disputed = byStatus("disputed");
  if (disputed) return booking(disputed, "worker.disputed", ic(CalendarCheck));
  const { identity } = dashboard;
  if (!identity.counts_here && identity.status !== "suspended") {
    return { key: "worker.verify", icon: ic(ShieldCheck), to: PATHS.workerVerify, action: "next.action.verify" };
  }
  const open = (inbox ?? []).find((item) => item.status === "active" && !item.booking);
  if (open) return { key: "worker.invitation", icon: ic(Inbox), to: `/worker/invitations/${open.id}`, action: "next.action.invitation" };
  if (!dashboard.profile.accepting_requests) {
    return { key: "worker.paused", icon: ic(Power), to: `${PATHS.worker}#accepting`, action: "next.action.settings" };
  }
  return { key: "worker.idle", icon: ic(CircleCheck), to: PATHS.workerProfile, action: "next.action.profile" };
}

export function customerNextStep(jobs: JobListItem[] | null, bookings: bookingsApi.BookingCard[] | null): Step {
  const mine = (bookings ?? []).filter((card) => card.role === "customer");
  const find = (status: bookingsApi.BookingStatus) => mine.find((card) => card.status === status);
  const arrived = find("arrived");
  if (arrived) return { key: "customer.code", icon: ic(KeyRound), to: `/bookings/${arrived.id}`, action: "next.action.booking" };
  const awaiting = find("completion_requested");
  if (awaiting) return { key: "customer.confirm", icon: ic(CircleCheck), to: `/bookings/${awaiting.id}`, action: "next.action.booking" };
  const review = mine.find((card) => card.status === "completed" && !card.review_submitted);
  if (review) return { key: "customer.review", icon: ic(Star), to: `/bookings/${review.id}`, action: "next.action.review" };
  const draft = (jobs ?? []).find((job) => job.status === "draft");
  if (draft) return { key: "customer.draft", icon: ic(ClipboardList), to: `/customer/requests/${draft.id}/details`, action: "next.action.draft" };
  const waiting = (jobs ?? []).find((job) => job.status === "confirmed" && !job.booking);
  if (waiting) return { key: "customer.find", icon: ic(Users), to: `/customer/requests/${waiting.id}/workers`, action: "next.action.find" };
  return { key: "customer.new", icon: ic(MessageSquarePlus), to: PATHS.newJob, action: "next.action.describe" };
}

function StepCard({ step }: { step: Step }) {
  const { t } = useI18n();
  return (
    <section aria-labelledby="next-step-heading" className="card relative overflow-hidden p-4 sm:p-5">
      <span className="absolute inset-y-0 start-0 w-1.5 bg-accent" aria-hidden />
      <div className="flex items-start gap-3 ps-1">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-accent-soft text-warning-strong">{step.icon}</span>
        <div className="min-w-0 flex-1 space-y-1">
          <p id="next-step-heading" className="text-sm font-bold text-muted">{t("next.heading")}</p>
          <h2 className="text-lg font-bold">{t(`next.${step.key}.title` as TranslationKey)}</h2>
          <p className="text-muted">{t(`next.${step.key}.body` as TranslationKey)}</p>
        </div>
      </div>
      <div className="mt-3 flex justify-end">
        <ButtonLink to={step.to} variant="gold" icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />}>
          {t(step.action)}
        </ButtonLink>
      </div>
    </section>
  );
}

/** Worker: the most relevant next action from bookings, verification, invitations and the accepting switch. */
export function WorkerNextStep({ dashboard }: { dashboard: WorkerDashboard }) {
  const data = useLoad((signal) => Promise.all([settle(bookingsApi.listBookings(signal)), settle(invitationsApi.fetchInbox(signal))]));
  if (data.state.status !== "ready") return null;
  const [bookings, inbox] = data.state.data;
  const step = workerNextStep(dashboard, bookings?.results ?? null, inbox?.results ?? null);
  // "Verify your identity" is already the dashboard's one notice near the top: no second card saying the same.
  if (step.key === "worker.verify") return null;
  return <StepCard step={step} />;
}

/** Customer: the most relevant next action from bookings and requests. */
export function CustomerNextStep({ jobs }: { jobs: JobListItem[] | null }) {
  const data = useLoad((signal) => settle(bookingsApi.listBookings(signal)));
  if (data.state.status !== "ready") return null;
  return <StepCard step={customerNextStep(jobs, data.state.data?.results ?? null)} />;
}
