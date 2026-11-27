import { ArrowLeft, CalendarCheck, Eye, EyeOff, MessagesSquare, Save, Send, ShieldCheck, Sparkles, UserRound, X } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";

import { ApiError } from "../../api/client";
import * as invitationsApi from "../../api/invitations";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { SharedJob } from "../../features/invitations/SharedJob";
import { type JobCatalog, labeller, loadJobCatalog } from "../../features/jobs/catalog";
import { textDir } from "../../features/jobs/text";
import { formatDate, formatTime } from "../../features/jobs/time";
import { LoadError, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";

const VERIFICATION_KEYS = {
  demo_approved: "rec.verification.demo_approved",
  provider_verified: "rec.verification.provider_verified",
  manually_reviewed: "rec.verification.manually_reviewed",
} as const;

function workerTitle(trade: string | null, workerId: string, catalog: JobCatalog, language: "ur" | "en", t: ReturnType<typeof useI18n>["t"]) {
  return `${labeller(catalog, language).trade(trade)} · ${t("rec.ref")} ${invitationsApi.workerRef(workerId)}`;
}

/** Customer: matching workers, why they match, preview of what is shared, one active invitation. */
export function FindWorkersPage() {
  const { id = "" } = useParams();
  const data = useLoad(
    (signal) => Promise.all([invitationsApi.fetchRecommendations(id, signal), loadJobCatalog(signal), invitationsApi.fetchJobInvitations(id, signal)]),
    [id],
  );
  const { t } = useI18n();
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") {
    const notConfirmed = data.state.error instanceof ApiError && data.state.error.code === "request_not_confirmed";
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-bold text-primary">{t("rec.title")}</h1>
        {notConfirmed ? <Alert tone="warning">{t("errors.request_not_confirmed")}</Alert> : <LoadError error={data.state.error} onRetry={data.retry} />}
        <ButtonLink to={`/customer/requests/${id}`} variant="secondary" icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
          {t("rec.backToRequest")}
        </ButtonLink>
      </div>
    );
  }
  const [recs, catalog, history] = data.state.data;
  return <Workers jobId={id} recs={recs} catalog={catalog} history={history.results} reload={data.retry} />;
}

function Workers({ jobId, recs, catalog, history, reload }: {
  jobId: string;
  recs: invitationsApi.Recommendations;
  catalog: JobCatalog;
  history: invitationsApi.CustomerInvitation[];
  reload: () => void;
}) {
  const { t, language } = useI18n();
  const label = labeller(catalog, language);
  const [previewFor, setPreviewFor] = useState<string | null>(null);
  const [busy, setBusy] = useState<"send" | "withdraw" | "description" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [description, setDescription] = useState(recs.shared_preview.description);
  const [savedDescription, setSavedDescription] = useState(recs.shared_preview.description);
  const [warnings, setWarnings] = useState(recs.privacy_warnings);
  // Warnings describe the SAVED text; while the customer is editing they would be stale.
  const dirty = description.trim() !== savedDescription.trim();
  const active = recs.active_invitation;
  const separator = language === "ur" ? "، " : ", ";
  const services = (codes: string[]) => codes.map(label.service).join(separator);

  async function act(kind: NonNullable<typeof busy>, action: () => Promise<unknown>) {
    setFailure(null);
    setBusy(kind);
    try {
      await action();
      if (kind !== "description") {
        setPreviewFor(null);
        reload();
      }
    } catch (error) {
      setFailure(error);
      if (error instanceof ApiError && error.code === "invitation_already_active") reload();
    } finally {
      setBusy(null);
    }
  }

  const saveDescription = () =>
    act("description", async () => {
      const updated = await invitationsApi.updateSharedDescription(jobId, description);
      setWarnings(updated.privacy_warnings as typeof warnings);
      setSavedDescription(updated.details.description);
    });

  const closedHistory = history.filter((item) => item.status !== "active");

  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-bold text-primary">{t("rec.title")}</h1>
      <p className="text-muted">{t("rec.intro")}</p>

      <section aria-labelledby="request-heading" className="space-y-1 rounded-2xl border border-line bg-surface p-4">
        <h2 id="request-heading" className="font-bold">{t("rec.yourRequest")}</h2>
        <p>{`${label.trade(recs.request.trade)}: ${services(recs.request.services)}`}</p>
        <p>{`${label.area(recs.request.area)}${separator}${label.city(recs.request.city)}`}</p>
        <p className="flex flex-wrap items-center gap-x-2">
          <span>{t("rec.requestedTime")}:</span>
          <span>{formatDate(recs.request.window_start, language)}</span>
          <bdi dir="ltr">{`${formatTime(recs.request.window_start, language)} – ${formatTime(recs.request.window_end, language)}`}</bdi>
        </p>
        <p className="text-sm text-muted">{t("rec.requestedTimeNote")}</p>
      </section>

      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      {active && (
        <section aria-labelledby="active-heading" className="space-y-3 rounded-2xl border-2 border-primary bg-white p-4">
          <h2 id="active-heading" className="flex items-center gap-2 text-lg font-bold">
            <Send className="size-5" aria-hidden />
            {t("rec.active.title")}
          </h2>
          <p className="font-bold">{workerTitle(active.worker.trade, active.worker.worker_id, catalog, language, t)}</p>
          <div className="flex flex-wrap gap-2">
            <StatusBadge tone="info">{t("inv.status.active")}</StatusBadge>
            <StatusBadge tone={active.seen_at ? "success" : "neutral"} icon={active.seen_at ? <Eye className="size-4" aria-hidden /> : <EyeOff className="size-4" aria-hidden />}>
              {active.seen_at ? t("rec.active.seen") : t("rec.active.notSeen")}
            </StatusBadge>
          </div>
          <p className="text-sm text-muted">{t("rec.notABooking")}</p>
          {active.booking && (
            <ButtonLink to={`/bookings/${active.booking.id}`} fullWidth icon={<CalendarCheck className="size-5" aria-hidden />}>
              {t("booking.open")} · {t(`booking.status.${active.booking.status}`)}
            </ButtonLink>
          )}
          <ButtonLink to={`/conversations/${active.id}`} fullWidth variant={active.booking ? "secondary" : "primary"} icon={<MessagesSquare className="size-5" aria-hidden />}>
            {t("conv.open")}
          </ButtonLink>
          {!active.booking && <Button variant="secondary" loading={busy === "withdraw"} loadingLabel={t("onboarding.saving")} icon={<X className="size-5" aria-hidden />}
            onClick={() => void act("withdraw", () => invitationsApi.withdrawInvitation(jobId, active.id))}>
            {t("rec.active.withdraw")}
          </Button>}
        </section>
      )}

      <section aria-labelledby="workers-heading" className="space-y-3">
        <h2 id="workers-heading" className="text-lg font-bold">{t("rec.list.heading", { count: recs.workers.length })}</h2>
        <p className="text-sm text-muted">{t("rec.declarations")}</p>
        {recs.workers.length === 0 ? (
          <Alert tone="info" title={t("rec.empty.title")}>
            <p>{t("rec.empty.body", { services: services(recs.request.services), area: label.area(recs.request.area) })}</p>
          </Alert>
        ) : (
          <ul className="space-y-3">
            {recs.workers.map((card) => {
              const invitedHere = active?.worker.worker_id === card.worker_id;
              const verification = VERIFICATION_KEYS[card.verification.status as keyof typeof VERIFICATION_KEYS];
              return (
                <li key={card.worker_id} className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <UserRound className="size-5 text-primary" aria-hidden />
                    <span className="font-bold">{workerTitle(card.trade, card.worker_id, catalog, language, t)}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {verification && (
                      <StatusBadge tone={card.verification.simulated ? "warning" : "success"} icon={<ShieldCheck className="size-4" aria-hidden />}>
                        {t(verification)}
                      </StatusBadge>
                    )}
                    {card.is_new && <StatusBadge tone="neutral" icon={<Sparkles className="size-4" aria-hidden />}>{t("rec.new")}</StatusBadge>}
                    {invitedHere && <StatusBadge tone="info">{t("rec.invited")}</StatusBadge>}
                  </div>
                  <ul className="list-inside list-disc space-y-1">
                    {card.reasons.map((reason) => (
                      <li key={reason.code}>
                        {reason.code === "speciality" && t("rec.reason.speciality", { services: services(reason.services) })}
                        {reason.code === "offers" && t("rec.reason.offers", { services: services(reason.services) })}
                        {reason.code === "serves_area" && t("rec.reason.servesArea", { area: label.area(reason.area) })}
                      </li>
                    ))}
                  </ul>
                  {card.is_new && <p className="text-sm text-muted">{t("rec.newNote")}</p>}
                  {card.previous_invitation === "declined" && <p className="text-sm text-muted">{t("rec.previous.declined")}</p>}
                  {card.previous_invitation === "withdrawn" && <p className="text-sm text-muted">{t("rec.previous.withdrawn")}</p>}
                  {!active && (
                    <Button variant={previewFor === card.worker_id ? "secondary" : "primary"} icon={<Eye className="size-5" aria-hidden />}
                      onClick={() => setPreviewFor(previewFor === card.worker_id ? null : card.worker_id)}>
                      {t("rec.invite")}
                    </Button>
                  )}

                  {previewFor === card.worker_id && !active && (
                    <section aria-label={t("rec.preview.title")} className="space-y-3 rounded-2xl border-2 border-primary/40 bg-surface p-3">
                      <h3 className="font-bold">{t("rec.preview.title")}</h3>
                      <p className="text-sm">{t("rec.preview.intro")}</p>
                      <SharedJob job={{ ...recs.shared_preview, description }} catalog={catalog} />
                      <Alert tone="info" title={t("rec.preview.notShared.title")}>{t("rec.preview.notShared.body")}</Alert>
                      <Alert tone={warnings.length && !dirty ? "warning" : "info"} title={t("rec.preview.reminder.title")}>
                        <p>{t("rec.preview.reminder.body")}</p>
                        {!dirty && warnings.includes("phone_number") && <p className="font-bold">{t("rec.preview.warning.phone")}</p>}
                        {!dirty && warnings.includes("address") && <p className="font-bold">{t("rec.preview.warning.address")}</p>}
                        {dirty && <p className="font-bold">{t("rec.preview.unsaved")}</p>}
                      </Alert>
                      <TextArea label={t("rec.preview.editDescription")} value={description} onChange={setDescription} maxLength={2000} rows={3} dir={textDir(description)} />
                      <Button variant="secondary" loading={busy === "description"} loadingLabel={t("onboarding.saving")} disabled={!dirty || busy !== null}
                        icon={<Save className="size-5" aria-hidden />} onClick={() => void saveDescription()}>
                        {t("rec.preview.saveDescription")}
                      </Button>
                      <p className="text-sm text-muted">{t("rec.notABooking")}</p>
                      <Button fullWidth loading={busy === "send"} loadingLabel={t("onboarding.saving")} icon={<Send className="size-5" aria-hidden />}
                        onClick={() => void act("send", async () => {
                          if (dirty) await invitationsApi.updateSharedDescription(jobId, description);
                          await invitationsApi.sendInvitation(jobId, card.worker_id);
                        })}>
                        {t("rec.preview.send")}
                      </Button>
                    </section>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {closedHistory.length > 0 && (
        <section aria-labelledby="history-heading" className="space-y-2">
          <h2 id="history-heading" className="font-bold">{t("rec.history")}</h2>
          <ul className="space-y-2">
            {closedHistory.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2 text-sm">
                <span>{workerTitle(item.worker.trade, item.worker.worker_id, catalog, language, t)}</span>
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone="neutral">{t(`inv.status.${item.status}`)}</StatusBadge>
                  <ButtonLink to={`/conversations/${item.id}`} variant="ghost" icon={<MessagesSquare className="size-4" aria-hidden />}>
                    {t("conv.view")}
                  </ButtonLink>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <ButtonLink to={`/customer/requests/${jobId}`} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("rec.backToRequest")}
      </ButtonLink>
    </div>
  );
}
