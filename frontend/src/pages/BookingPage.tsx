import { CalendarClock, ClipboardList, FilePen, FileText, History, MapPin, MessagesSquare, ShieldCheck } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";

import * as bookingsApi from "../api/bookings";
import { ConnectionError } from "../api/client";
import { workerRef } from "../api/invitations";
import { Ltr } from "../components/Ltr";
import { Alert } from "../components/ui/Alert";
import { ButtonLink } from "../components/ui/Button";
import { PageLoader } from "../components/ui/PageLoader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { ArrivalPanel } from "../features/bookings/ArrivalPanel";
import { CancelPanel } from "../features/bookings/CancelPanel";
import { ChangesPanel } from "../features/bookings/ChangesPanel";
import { CompletionPanel } from "../features/bookings/CompletionPanel";
import { ReviewPanel } from "../features/bookings/ReviewPanel";
import { QuoteFacts, TermsRows } from "../features/conversations/QuotePanel";
import { quoteSpeech } from "../features/conversations/quoteText";
import { SharedJob } from "../features/invitations/SharedJob";
import { JobStages, stagePath } from "../features/jobs/JobStages";
import { type JobCatalog, labeller, loadJobCatalog } from "../features/jobs/catalog";
import { textDir } from "../features/jobs/text";
import { formatDate, formatTime } from "../features/jobs/time";
import { SafetyPanel } from "../features/reports/SafetyPanel";
import { ReadAloud } from "../features/voice/ReadAloud";
import { LoadError } from "../features/worker/shared";
import { isTranslationKey, useI18n } from "../i18n/context";
import { describeError } from "../i18n/errors";
import type { TranslationKey } from "../i18n/types";

const POLL_MS = 10000;

/** Load the booking and refresh it quietly (the other person may act meanwhile); typed input is never reset. */
function useBooking(id: string) {
  const [booking, setBooking] = useState<bookingsApi.Booking | null>(null);
  const [catalog, setCatalog] = useState<JobCatalog | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const settle = useCallback((next: bookingsApi.Booking) => {
    const { code: _shownOnce, created: _created, ...rest } = next; // the plaintext code never goes into page state
    setBooking(rest);
    setError(null);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    loadJobCatalog(controller.signal).then(setCatalog).catch(() => undefined);
    const load = () => bookingsApi.fetchBooking(id, controller.signal).then(settle)
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure); });
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [id, attempt, settle]);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { booking, catalog, error, reload, settle };
}

/** One line under the status, only where no action panel below already explains the next step. */
function nextLine(booking: bookingsApi.Booking): TranslationKey | null {
  if (booking.role === "customer" && booking.status === "in_progress") return "booking.inProgressBody";
  return null;
}

function Secondary({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <details className="card p-3 sm:px-4">
      <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold">{icon}{title}</summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}

/**
 * Work progress: one booking, seen by its customer and its assigned worker. The real status and this person's next
 * action (arrival, code, start, completion, review) come first; the time, address and price beside them; full terms,
 * changes, past events and the request behind "View" sections. Report, block and cancel stay on the page.
 */
export function BookingPage() {
  const { id = "" } = useParams();
  const { t, language } = useI18n();
  const { booking, catalog, error, reload, settle } = useBooking(id);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [uncertain, setUncertain] = useState(false);

  const act = useCallback(async (action: () => Promise<bookingsApi.Booking>, options: { showError?: boolean } = {}) => {
    setFailure(null);
    setUncertain(false);
    setBusy(true);
    try {
      settle(await action());
      return true;
    } catch (err) {
      if (err instanceof ConnectionError) {
        setUncertain(true); // the outcome is unknown: show the server's state before anything is retried
        reload();
      } else if (options.showError !== false) {
        setFailure(err);
        reload();
      }
      return false;
    } finally {
      setBusy(false);
    }
  }, [reload, settle]);

  if (!booking) return error ? <LoadError error={error} onRetry={reload} /> : <PageLoader />;
  const role = booking.role;
  const label = catalog ? labeller(catalog, language) : null;
  const counterpart = booking.counterpart;
  const when = `${formatTime(booking.start_at, language)} – ${formatTime(booking.end_at, language)}`;
  const cancelKey = booking.cancel_reason ? `cancel.reason.${booking.cancel_reason}` : null;
  const next = nextLine(booking);
  const pendingChange = booking.changes.some((change) => change.status === "pending");
  const showChanges = booking.actions.propose_change || booking.changes.length > 0;
  const verification = counterpart.role === "worker" ? counterpart.verification : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("stage.work")}</h1>
        {counterpart.role === "worker" ? (
          <p className="flex flex-wrap items-center gap-2 text-muted">
            <span>{t("conv.with", { name: `${label ? label.trade(counterpart.trade) : ""} · ${t("rec.ref")} ${workerRef(counterpart.worker_id)}` })}</span>
            {verification?.status && (
              <StatusBadge tone={verification.simulated ? "neutral" : "success"} icon={<ShieldCheck className="size-4" aria-hidden />}>
                {isTranslationKey(`rec.verification.${verification.status}`) ? t(`rec.verification.${verification.status}` as never) : verification.status}
              </StatusBadge>
            )}
          </p>
        ) : (
          <p className="text-muted">{t("booking.withCustomer")}</p>
        )}
      </div>
      <JobStages current="work" facts={{
        invitationId: booking.invitation_id, role, acceptedVersion: booking.quote_version, booking: { id: booking.id, status: booking.status },
      }} />

      {uncertain && <Alert tone="warning" title={t("booking.uncertainTitle")}>{t("booking.uncertainBody")}</Alert>}
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,24rem)] lg:grid-rows-[auto_1fr]">
        <div className="min-w-0 space-y-4 lg:col-start-1 lg:row-start-1">
          <section aria-labelledby="work-status" className="card space-y-1 p-4 sm:p-5">
            <p className="text-sm text-muted">{t("work.statusLabel")}</p>
            <h2 id="work-status" className="text-2xl font-bold">{t(`booking.status.${booking.status}`)}</h2>
            {booking.status === "cancelled" ? (
              <div className="space-y-1 pt-1">
                <p className="font-bold">{t("booking.cancelledTitle", { role: t(`conv.role.${booking.cancelled_role ?? "customer"}`) })}</p>
                {cancelKey && isTranslationKey(cancelKey) && <p>{t(cancelKey)}</p>}
                {booking.cancel_note && <p dir={textDir(booking.cancel_note)}>“{booking.cancel_note}”</p>}
                <p className="text-sm text-muted">{t("booking.cancelledNext")}</p>
              </div>
            ) : next && !booking.staff_outcome ? (
              <p className="font-bold text-primary">{t(next)}</p>
            ) : null}
          </section>

          <ArrivalPanel booking={booking} act={act} busy={busy} />
          <CompletionPanel booking={booking} act={act} busy={busy} />
          <ReviewPanel booking={booking} onDone={reload} />
          {pendingChange && <div className="card p-4"><ChangesPanel booking={booking} act={act} busy={busy} /></div>}
        </div>

        <aside aria-label={t("work.facts")} className="min-w-0 space-y-3 lg:sticky lg:top-24 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <section className="card space-y-3 p-4">
            <div>
              <h2 className="flex items-center gap-2 text-sm text-muted"><CalendarClock className="size-4" aria-hidden />{t("booking.when")}</h2>
              <p className="font-bold">{formatDate(booking.start_at, language)}</p>
              <Ltr className="font-bold">{when}</Ltr>
              <p className="text-xs text-muted">{t("jobs.time.zoneNote")}</p>
            </div>
            {booking.address && (
              <div className="border-t border-line pt-3">
                <h2 className="flex items-center gap-2 text-sm text-muted"><MapPin className="size-4" aria-hidden />{t(role === "worker" ? "booking.addressWorker" : "booking.addressCustomer")}</h2>
                <p dir={textDir(booking.address.address)} className="whitespace-pre-line font-bold">{booking.address.address}</p>
                {booking.address.access_notes && <p dir={textDir(booking.address.access_notes)} className="text-sm">{booking.address.access_notes}</p>}
                <p className="text-xs text-muted">{t(role === "worker" ? "booking.addressWorkerNote" : "booking.addressCustomerNote")}</p>
              </div>
            )}
            <div className="border-t border-line pt-3">
              <QuoteFacts quote={booking.terms} withTime={false} />
            </div>
            <ButtonLink to={stagePath.chat(booking.invitation_id)} variant="secondary" fullWidth icon={<MessagesSquare className="size-5" aria-hidden />}>
              {t("booking.conversation")}
            </ButtonLink>
          </section>
          <SafetyPanel target={{ booking_id: booking.id }} block={booking.contact_block} onChanged={reload} />
          <CancelPanel booking={booking} act={act} busy={busy} />
        </aside>

        <div className="min-w-0 space-y-3 lg:col-start-1 lg:row-start-2">
          <Secondary icon={<FileText className="size-5" aria-hidden />} title={t("work.fullTerms")}>
            <StatusBadge tone="info">
              {booking.terms_changed ? t("booking.termsAfterChange", { number: booking.terms.source?.kind === "change" ? booking.terms.source.number : "" })
                : t("booking.termsAccepted", { version: booking.quote_version })}
            </StatusBadge>
            <dl className="space-y-3"><TermsRows quote={booking.terms} /></dl>
            <ReadAloud text={quoteSpeech({ ...booking.terms, version: booking.quote_version } as never, language, t)} language={language} showText={false} />
            {booking.terms_changed && (
              <details className="rounded-2xl border border-line bg-surface p-3">
                <summary className="flex min-h-11 cursor-pointer items-center font-bold">{t("booking.original", { version: booking.quote_version })}</summary>
                <dl className="mt-3 space-y-3"><TermsRows quote={booking.accepted_terms} /></dl>
              </details>
            )}
          </Secondary>
          {showChanges && !pendingChange && (
            <Secondary icon={<FilePen className="size-5" aria-hidden />} title={booking.changes.length ? t("work.changesCount", { count: booking.changes.length }) : t("change.title")}>
              <ChangesPanel booking={booking} act={act} busy={busy} heading={false} />
            </Secondary>
          )}
          <Secondary icon={<History className="size-5" aria-hidden />} title={t("work.pastEvents", { count: booking.history.length })}>
            <ol className="space-y-1 text-sm">
              {booking.history.map((event, index) => (
                <li key={`${event.kind}-${index}`} className="rounded-lg bg-surface p-2">
                  <span className="font-bold">{t(`booking.event.${event.kind}`)}</span>
                  {event.actor_role && <span> · {t(`booking.actor.${event.actor_role}`)}</span>}
                  <span className="block text-muted">{formatDate(event.at, language)} <bdi dir="ltr">{formatTime(event.at, language)}</bdi></span>
                </li>
              ))}
            </ol>
          </Secondary>
          <Secondary icon={<ClipboardList className="size-5" aria-hidden />} title={t("conv.viewRequest")}>
            {catalog && <SharedJob job={booking.job} catalog={catalog} plain />}
          </Secondary>
        </div>
      </div>
    </div>
  );
}
