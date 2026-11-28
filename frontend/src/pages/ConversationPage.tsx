import { CalendarCheck, Clock, FileText, PencilLine } from "lucide-react";
import { useCallback, useState } from "react";
import { Outlet, useMatches, useOutletContext, useParams } from "react-router";

import type { BookingStatus } from "../api/bookings";
import * as convApi from "../api/conversations";
import { workerRef } from "../api/invitations";
import { Ltr } from "../components/Ltr";
import { Alert } from "../components/ui/Alert";
import { Button, ButtonLink } from "../components/ui/Button";
import { PageLoader } from "../components/ui/PageLoader";
import { readDraft } from "../features/drafts";
import { JobBrief } from "../features/conversations/JobBrief";
import { MessageThread } from "../features/conversations/MessageThread";
import { QuotePanel, type QuotesState, useQuotes } from "../features/conversations/QuotePanel";
import { quoteFormDraftKey } from "../features/conversations/QuoteForm";
import { money } from "../features/conversations/quoteText";
import { JobStages, type JobStage, stagePath } from "../features/jobs/JobStages";
import { type JobCatalog, labeller, loadJobCatalog } from "../features/jobs/catalog";
import { SafetyPanel } from "../features/reports/SafetyPanel";
import { LoadError, useLoad } from "../features/worker/shared";
import { useI18n } from "../i18n/context";

export interface ConversationContext {
  header: convApi.ConversationHeader;
  catalog: JobCatalog;
  /** One quote poll for the whole invitation, shared by both screens and the stage header. */
  quotes: QuotesState;
  canWrite: boolean;
  /** The booking made from this invitation, from the header or (when it happened meanwhile) the quote readiness. */
  booking: { id: string; status: BookingStatus | null } | null;
  booked: boolean;
  bump: () => void;
  closed: () => void;
  reload: () => void;
}

/** Old and new links alike: a new invitation id mounts a fresh layout (no state carried between invitations). */
export function ConversationRoute() {
  const { id = "" } = useParams();
  return <ConversationLayout key={id} id={id} />;
}

/**
 * One invitation's first two stages: Request & chat (`/conversations/:id`) and Quote (`/conversations/:id/quote`).
 * The header, catalog and quote poll load once here, so moving between the two screens adds no requests.
 */
function ConversationLayout({ id }: { id: string }) {
  const { t, language } = useI18n();
  const matches = useMatches();
  const stage: JobStage = matches.some((match) => (match.handle as { stage?: JobStage } | undefined)?.stage === "quote") ? "quote" : "chat";
  const data = useLoad((signal) => Promise.all([convApi.fetchConversation(id, signal), loadJobCatalog(signal)]), [id]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [closedNow, setClosedNow] = useState(false);
  const bump = useCallback(() => setRefreshKey((n) => n + 1), []);
  const closed = useCallback(() => { setClosedNow(true); setRefreshKey((n) => n + 1); }, []);
  const quotes = useQuotes(id, refreshKey);

  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [header, catalog] = data.state.data;
  const canWrite = header.can_write && !closedNow;
  const label = labeller(catalog, language);
  const counterpart =
    header.counterpart.role === "worker"
      ? `${label.trade(header.counterpart.trade)} · ${t("rec.ref")} ${workerRef(header.counterpart.worker_id)}`
      : t("conv.role.customer");
  const acceptedId = quotes.listing?.readiness.booking_id ?? null;
  const booking = header.booking ?? (acceptedId ? { id: acceptedId, status: null } : null);
  const booked = Boolean(booking && booking.status !== "cancelled");
  const context: ConversationContext = { header, catalog, quotes, canWrite, booking, booked, bump, closed, reload: data.retry };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{stage === "quote" ? t("quote.title") : t("conv.title")}</h1>
        <p className="text-muted">{t("conv.with", { name: counterpart })}</p>
      </div>
      <JobStages current={stage} facts={{
        invitationId: header.invitation.id, role: header.role, chatOpen: header.invitation.status === "active" && !closedNow,
        quote: quotes.listing ?? (quotes.error ? null : undefined), booking,
      }} />
      {!canWrite && (
        <Alert tone="info">
          {header.write_blocked_reason === "contact_blocked" ? t("conv.blockedBody")
            : header.write_blocked_reason === "account_restricted" ? t("conv.restrictedBody") : t("conv.closedBody")}
        </Alert>
      )}
      <Outlet context={context} />
    </div>
  );
}

export const useConversation = () => useOutletContext<ConversationContext>();

/** The one thing to do next from the chat: open the booking, prepare or view the quote, or wait for it. */
function ChatNextAction({ context }: { context: ConversationContext }) {
  const { t } = useI18n();
  const { header, quotes, canWrite, booking, booked } = context;
  const id = header.invitation.id;
  if (booking && booked) {
    return (
      <section className="card-action space-y-2 p-4">
        <p className="flex items-center gap-2 font-bold"><CalendarCheck className="size-5 text-primary" aria-hidden />
          {t("stage.work")}: {booking.status ? t(`booking.status.${booking.status}`) : t("booking.status.confirmed")}</p>
        <ButtonLink to={stagePath.work(booking.id)} fullWidth icon={<CalendarCheck className="size-5" aria-hidden />}>{t("stage.openWork")}</ButtonLink>
      </section>
    );
  }
  if (!quotes.listing) {
    return quotes.error ? (
      <section className="card space-y-2 p-4">
        <p className="text-sm">{t("quote.statusFailed")}</p>
        <Button variant="secondary" onClick={quotes.reload}>{t("common.retry")}</Button>
      </section>
    ) : null;
  }
  const { current, draft, readiness } = quotes.listing;
  if (!current) {
    if (header.role === "customer") {
      return (
        <p role="status" className="card flex items-center gap-2 p-4 font-bold">
          <Clock className="size-5 shrink-0 text-primary" aria-hidden />
          {t("quote.waiting")}
        </p>
      );
    }
    const continuing = Boolean(draft) || readDraft(quoteFormDraftKey(id)) !== undefined;
    return (
      <section className="card-action space-y-2 p-4">
        <p className="text-sm">{t("quote.none.worker")}</p>
        {canWrite && (
          <ButtonLink to={stagePath.quote(id, true)} fullWidth icon={<PencilLine className="size-5" aria-hidden />}>
            {continuing ? t("quote.continueDraft") : t("quote.create")}
          </ButtonLink>
        )}
      </section>
    );
  }
  return (
    <section className="card-action space-y-2 p-4">
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-bold">{t("quote.versionLabel", { version: current.version ?? "–" })}</span>
        <Ltr className="font-bold">{money(current.totals?.known_total) ?? ""}</Ltr>
      </p>
      <p className={`text-sm font-bold ${readiness.ready ? "text-success-strong" : "text-warning-strong"}`}>
        {readiness.ready ? t("quote.summary.ready") : t("quote.summary.blocked")}
      </p>
      <ButtonLink to={stagePath.quote(id)} fullWidth icon={<FileText className="size-5" aria-hidden />}>{t("quote.view")}</ButtonLink>
    </section>
  );
}

/** Request & chat: the conversation and composer, a compact request summary and the next action. No quote form here. */
export function ChatStage() {
  const context = useConversation();
  const { header, catalog, canWrite, bump, closed, reload } = context;
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:grid-rows-[auto_auto_1fr] xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="min-w-0 lg:col-start-2 lg:row-start-1">
        <ChatNextAction context={context} />
      </div>
      <div className="min-w-0 lg:col-start-1 lg:row-span-3 lg:row-start-1">
        <MessageThread invitationId={header.invitation.id} canWrite={canWrite} onActivity={bump} onClosed={closed} />
      </div>
      <div className="min-w-0 lg:col-start-2 lg:row-start-2">
        <JobBrief job={header.job} catalog={catalog} />
      </div>
      <div className="min-w-0 lg:col-start-2 lg:row-start-3">
        <SafetyPanel target={{ invitation_id: header.invitation.id }} block={header.contact_block} onChanged={reload} />
      </div>
    </div>
  );
}

/** Quote: the dedicated screen for the same invitation (both roles). No chat thread here. */
export function QuoteStage() {
  const { header, catalog, canWrite, quotes, booked, booking } = useConversation();
  return (
    <QuotePanel invitationId={header.invitation.id} role={header.role} canWrite={canWrite} data={quotes} booked={booked}
      bookingId={booked ? booking?.id ?? null : null} brief={<JobBrief job={header.job} catalog={catalog} />} />
  );
}
