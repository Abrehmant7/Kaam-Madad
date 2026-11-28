import { ArrowLeft, CalendarCheck, MessagesSquare } from "lucide-react";
import { useCallback, useState } from "react";
import { useParams } from "react-router";

import * as convApi from "../api/conversations";
import { workerRef } from "../api/invitations";
import { Alert } from "../components/ui/Alert";
import { ButtonLink } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { PageLoader } from "../components/ui/PageLoader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { MessageThread } from "../features/conversations/MessageThread";
import { QuotePanel, QuoteSummary, useQuotes } from "../features/conversations/QuotePanel";
import { SharedJob } from "../features/invitations/SharedJob";
import { SafetyPanel } from "../features/reports/SafetyPanel";
import { labeller, loadJobCatalog } from "../features/jobs/catalog";
import { LoadError, useLoad } from "../features/worker/shared";
import { useI18n } from "../i18n/context";

/**
 * M7: private conversation and quotation for one invitation (the job owner and the invited worker only).
 * Desktop: the chat beside the quote terms. Mobile: a compact quote summary (total, materials, blocking issues) first,
 * then the chat, then the full quote with its check and the accept action.
 */
export function ConversationPage() {
  const { id = "" } = useParams();
  const { t, language } = useI18n();
  const data = useLoad((signal) => Promise.all([convApi.fetchConversation(id, signal), loadJobCatalog(signal)]), [id]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [closedNow, setClosedNow] = useState(false);
  const bump = useCallback(() => setRefreshKey((n) => n + 1), []);
  const closed = useCallback(() => { setClosedNow(true); setRefreshKey((n) => n + 1); }, []);
  // One poll for the quote, shared by the summary and the panel (the route id is the invitation id).
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
  const back = header.role === "worker" ? `/worker/invitations/${header.invitation.id}` : header.job_id ? `/customer/requests/${header.job_id}/workers` : "/customer";
  const booked = Boolean(header.booking && header.booking.status !== "cancelled");

  return (
    <div className="space-y-5">
      <PageHeader icon={<MessagesSquare className="size-6" aria-hidden />} title={t("conv.title")} subtitle={t("conv.with", { name: counterpart })}>
        {header.invitation.status === "active" && !closedNow ? (
          <StatusBadge tone="info">{t("inv.status.active")}</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">{header.invitation.status === "active" ? t("conv.closedBadge") : t(`inv.status.${header.invitation.status}`)}</StatusBadge>
        )}
        <span className="text-sm text-muted">{t("conv.privacy")}</span>
      </PageHeader>
      {!canWrite && (
        <Alert tone="info">
          {header.write_blocked_reason === "contact_blocked" ? t("conv.blockedBody")
            : header.write_blocked_reason === "account_restricted" ? t("conv.restrictedBody") : t("conv.closedBody")}
        </Alert>
      )}
      {booked && header.booking && (
        <Alert tone="success" title={t("conv.bookedTitle")}>
          <p>{t("conv.bookedBody")}</p>
          <ButtonLink to={`/bookings/${header.booking.id}`} className="mt-2" icon={<CalendarCheck className="size-5" aria-hidden />}>
            {t("booking.open")} · {t(`booking.status.${header.booking.status}`)}
          </ButtonLink>
        </Alert>
      )}
      <details className="card p-3">
        <summary className="flex min-h-11 cursor-pointer items-center font-bold">{t("conv.jobDetails")}</summary>
        <div className="mt-3">
          <SharedJob job={header.job} catalog={catalog} />
        </div>
      </details>

      <div className="lg:hidden">
        <QuoteSummary data={quotes} />
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(20rem,1fr)]">
        <div className="min-w-0 space-y-5">
          <MessageThread invitationId={header.invitation.id} canWrite={canWrite} onActivity={bump} onClosed={closed} />
          <SafetyPanel target={{ invitation_id: header.invitation.id }} block={header.contact_block} onChanged={data.retry} />
        </div>
        <div className="min-w-0 lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto lg:pb-2">
          <QuotePanel invitationId={header.invitation.id} role={header.role} canWrite={canWrite} data={quotes} booked={booked} />
        </div>
      </div>

      <ButtonLink to={back} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("conv.back")}
      </ButtonLink>
    </div>
  );
}
