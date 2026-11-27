import { ArrowLeft, CalendarCheck, MessagesSquare } from "lucide-react";
import { useCallback, useState } from "react";
import { useParams } from "react-router";

import * as convApi from "../api/conversations";
import { workerRef } from "../api/invitations";
import { Alert } from "../components/ui/Alert";
import { ButtonLink } from "../components/ui/Button";
import { PageLoader } from "../components/ui/PageLoader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { MessageThread } from "../features/conversations/MessageThread";
import { QuotePanel } from "../features/conversations/QuotePanel";
import { SharedJob } from "../features/invitations/SharedJob";
import { SafetyPanel } from "../features/reports/SafetyPanel";
import { labeller, loadJobCatalog } from "../features/jobs/catalog";
import { LoadError, useLoad } from "../features/worker/shared";
import { useI18n } from "../i18n/context";

/** M7: private conversation and quotation for one invitation (the job owner and the invited worker only). */
export function ConversationPage() {
  const { id = "" } = useParams();
  const { t, language } = useI18n();
  const data = useLoad((signal) => Promise.all([convApi.fetchConversation(id, signal), loadJobCatalog(signal)]), [id]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [closedNow, setClosedNow] = useState(false);
  const bump = useCallback(() => setRefreshKey((n) => n + 1), []);
  const closed = useCallback(() => { setClosedNow(true); setRefreshKey((n) => n + 1); }, []);

  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [header, catalog] = data.state.data;
  const canWrite = header.can_write && !closedNow;
  const label = labeller(catalog, language);
  const counterpart =
    header.counterpart.role === "worker"
      ? `${label.trade(header.counterpart.trade)} · ${t("rec.ref")} ${workerRef(header.counterpart.worker_id)}`
      : t("conv.role.customer");
  const back = header.role === "worker" ? `/worker/invitations/${header.invitation.id}` : header.job_id ? `/customer/requests/${header.job_id}/workers` : "/customer";

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="flex items-center gap-2 text-3xl font-bold text-primary">
          <MessagesSquare className="size-7" aria-hidden />
          {t("conv.title")}
        </h1>
        <p className="font-bold">{t("conv.with", { name: counterpart })}</p>
        {header.invitation.status === "active" && !closedNow ? (
          <StatusBadge tone="info">{t("inv.status.active")}</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">{header.invitation.status === "active" ? t("conv.closedBadge") : t(`inv.status.${header.invitation.status}`)}</StatusBadge>
        )}
        <p className="text-sm text-muted">{t("conv.privacy")}</p>
      </div>
      {!canWrite && (
        <Alert tone="info">
          {header.write_blocked_reason === "contact_blocked" ? t("conv.blockedBody")
            : header.write_blocked_reason === "account_restricted" ? t("conv.restrictedBody") : t("conv.closedBody")}
        </Alert>
      )}
      {header.booking && header.booking.status !== "cancelled" && (
        <Alert tone="success" title={t("conv.bookedTitle")}>
          <p>{t("conv.bookedBody")}</p>
          <ButtonLink to={`/bookings/${header.booking.id}`} className="mt-2" icon={<CalendarCheck className="size-5" aria-hidden />}>
            {t("booking.open")} · {t(`booking.status.${header.booking.status}`)}
          </ButtonLink>
        </Alert>
      )}
      <details className="rounded-2xl border border-line bg-surface p-3">
        <summary className="flex min-h-11 cursor-pointer items-center font-bold">{t("conv.jobDetails")}</summary>
        <div className="mt-3">
          <SharedJob job={header.job} catalog={catalog} />
        </div>
      </details>

      <QuotePanel invitationId={header.invitation.id} role={header.role} canWrite={canWrite} refreshKey={refreshKey}
        booked={Boolean(header.booking && header.booking.status !== "cancelled")} />
      <MessageThread invitationId={header.invitation.id} canWrite={canWrite} onActivity={bump} onClosed={closed} />

      <SafetyPanel target={{ invitation_id: header.invitation.id }} block={header.contact_block} onChanged={data.retry} />

      <ButtonLink to={back} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("conv.back")}
      </ButtonLink>
    </div>
  );
}
