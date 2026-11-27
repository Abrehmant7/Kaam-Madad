import { ArrowLeft, CalendarCheck, CircleCheck, Circle, History, MapPin, MessagesSquare, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";

import * as bookingsApi from "../api/bookings";
import { ConnectionError } from "../api/client";
import { workerRef } from "../api/invitations";
import { useAuth } from "../auth/context";
import { Ltr } from "../components/Ltr";
import { Alert } from "../components/ui/Alert";
import { ButtonLink } from "../components/ui/Button";
import { PageLoader } from "../components/ui/PageLoader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { ArrivalPanel } from "../features/bookings/ArrivalPanel";
import { STATUS_TONE } from "../features/bookings/BookingList";
import { CancelPanel } from "../features/bookings/CancelPanel";
import { ChangesPanel } from "../features/bookings/ChangesPanel";
import { TermsRows } from "../features/conversations/QuotePanel";
import { quoteSpeech } from "../features/conversations/quoteText";
import { SharedJob } from "../features/invitations/SharedJob";
import { type JobCatalog, labeller, loadJobCatalog } from "../features/jobs/catalog";
import { textDir } from "../features/jobs/text";
import { formatDate, formatTime } from "../features/jobs/time";
import { ReadAloud } from "../features/voice/ReadAloud";
import { LoadError } from "../features/worker/shared";
import { isTranslationKey, useI18n } from "../i18n/context";
import { describeError } from "../i18n/errors";

const POLL_MS = 10000;
const STEPS = ["confirmed", "arrived", "in_progress"] as const;

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

function Steps({ status }: { status: bookingsApi.BookingStatus }) {
  const { t } = useI18n();
  const reached = STEPS.indexOf(status as (typeof STEPS)[number]);
  return (
    <ol className="grid grid-cols-3 gap-2 text-center text-sm" aria-label={t("booking.stepsLabel")}>
      {STEPS.map((step, index) => (
        <li key={step} className={`flex flex-col items-center gap-1 rounded-xl p-2 ${index <= reached ? "bg-primary/10 font-bold text-primary" : "text-muted"}`}
          aria-current={index === reached ? "step" : undefined}>
          {index <= reached ? <CircleCheck className="size-5" aria-hidden /> : <Circle className="size-5" aria-hidden />}
          {t(`booking.status.${step}`)}
        </li>
      ))}
    </ol>
  );
}

/** M8: one booking, seen by its customer and its assigned worker. */
export function BookingPage() {
  const { id = "" } = useParams();
  const { t, language } = useI18n();
  const { user } = useAuth();
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
  const back = user?.role === "worker" ? "/worker" : booking.job_id ? `/customer/requests/${booking.job_id}` : "/customer";
  const cancelKey = booking.cancel_reason ? `cancel.reason.${booking.cancel_reason}` : null;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="flex items-center gap-2 text-3xl font-bold text-primary">
          <CalendarCheck className="size-7" aria-hidden />
          {t("booking.title")}
        </h1>
        <StatusBadge tone={STATUS_TONE[booking.status]}>{t(`booking.status.${booking.status}`)}</StatusBadge>
        {counterpart.role === "worker" ? (
          <p className="flex flex-wrap items-center gap-2 font-bold">
            {label ? label.trade(counterpart.trade) : ""} · {t("rec.ref")} {workerRef(counterpart.worker_id)}
            {counterpart.verification.status && (
              <StatusBadge tone={counterpart.verification.simulated ? "warning" : "success"} icon={<ShieldCheck className="size-4" aria-hidden />}>
                {isTranslationKey(`rec.verification.${counterpart.verification.status}`) ? t(`rec.verification.${counterpart.verification.status}` as never) : counterpart.verification.status}
              </StatusBadge>
            )}
          </p>
        ) : (
          <p className="font-bold">{t("booking.withCustomer")}</p>
        )}
      </div>

      {uncertain && <Alert tone="warning" title={t("booking.uncertainTitle")}>{t("booking.uncertainBody")}</Alert>}
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      {booking.status === "cancelled" ? (
        <Alert tone="info" title={t("booking.cancelledTitle", { role: t(`conv.role.${booking.cancelled_role ?? "customer"}`) })}>
          {cancelKey && isTranslationKey(cancelKey) && <p>{t(cancelKey)}</p>}
          {booking.cancel_note && <p dir={textDir(booking.cancel_note)}>“{booking.cancel_note}”</p>}
          <p className="mt-1 text-sm">{t("booking.cancelledNext")}</p>
        </Alert>
      ) : (
        <Steps status={booking.status} />
      )}
      {booking.status === "in_progress" && <Alert tone="success" title={t("booking.inProgressTitle")}>{t("booking.inProgressBody")}</Alert>}

      <section className="space-y-1 rounded-2xl border border-line bg-white p-4">
        <h2 className="text-sm text-muted">{t("booking.when")}</h2>
        <p className="font-bold">{formatDate(booking.start_at, language)}</p>
        <Ltr className="font-bold">{when}</Ltr>
        <p className="text-sm text-muted">{t("jobs.time.zoneNote")}</p>
      </section>

      {booking.address && (
        <section className="space-y-1 rounded-2xl border border-line bg-white p-4">
          <h2 className="flex items-center gap-2 font-bold"><MapPin className="size-5" aria-hidden />{t(role === "worker" ? "booking.addressWorker" : "booking.addressCustomer")}</h2>
          <p dir={textDir(booking.address.address)} className="whitespace-pre-line">{booking.address.address}</p>
          {booking.address.access_notes && <p dir={textDir(booking.address.access_notes)} className="text-sm">{booking.address.access_notes}</p>}
          <p className="text-xs text-muted">{t(role === "worker" ? "booking.addressWorkerNote" : "booking.addressCustomerNote")}</p>
        </section>
      )}

      <ArrivalPanel booking={booking} act={act} busy={busy} />

      <section aria-labelledby="terms-heading" className="space-y-3">
        <h2 id="terms-heading" className="text-lg font-bold">{t("booking.terms")}</h2>
        <dl className="space-y-3 rounded-2xl border border-line bg-white p-4">
          <StatusBadge tone="info">
            {booking.terms_changed ? t("booking.termsAfterChange", { number: booking.terms.source?.kind === "change" ? booking.terms.source.number : "" })
              : t("booking.termsAccepted", { version: booking.quote_version })}
          </StatusBadge>
          <TermsRows quote={booking.terms} />
        </dl>
        <ReadAloud text={quoteSpeech({ ...booking.terms, version: booking.quote_version } as never, language, t)} language={language} />
        {booking.terms_changed && (
          <details className="rounded-2xl border border-line bg-surface p-3">
            <summary className="flex min-h-11 cursor-pointer items-center font-bold">{t("booking.original", { version: booking.quote_version })}</summary>
            <dl className="mt-3 space-y-3"><TermsRows quote={booking.accepted_terms} /></dl>
          </details>
        )}
        <details className="rounded-2xl border border-line bg-surface p-3">
          <summary className="flex min-h-11 cursor-pointer items-center font-bold">{t("conv.jobDetails")}</summary>
          <div className="mt-3">{catalog && <SharedJob job={booking.job} catalog={catalog} />}</div>
        </details>
      </section>

      {booking.status !== "cancelled" && <ChangesPanel booking={booking} act={act} busy={busy} />}
      <CancelPanel booking={booking} act={act} busy={busy} />

      <section aria-labelledby="history-heading" className="space-y-2">
        <h2 id="history-heading" className="flex items-center gap-2 text-lg font-bold"><History className="size-5" aria-hidden />{t("booking.history")}</h2>
        <ol className="space-y-1 text-sm">
          {booking.history.map((event, index) => (
            <li key={`${event.kind}-${index}`} className="rounded-lg bg-white p-2">
              <span className="font-bold">{t(`booking.event.${event.kind}`)}</span>
              {event.actor_role && <span> · {t(`conv.role.${event.actor_role}`)}</span>}
              <span className="block text-muted">{formatDate(event.at, language)} <bdi dir="ltr">{formatTime(event.at, language)}</bdi></span>
            </li>
          ))}
        </ol>
      </section>

      <ButtonLink to={`/conversations/${booking.invitation_id}`} variant="secondary" fullWidth icon={<MessagesSquare className="size-5" aria-hidden />}>
        {t("booking.conversation")}
      </ButtonLink>
      <ButtonLink to={back} variant="ghost" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("conv.back")}
      </ButtonLink>
    </div>
  );
}
