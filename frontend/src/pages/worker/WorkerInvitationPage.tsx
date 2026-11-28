import { ArrowLeft, Ban, CalendarCheck, Inbox, MessagesSquare } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";

import * as invitationsApi from "../../api/invitations";
import { PATHS } from "../../auth/paths";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { PageHeader } from "../../components/ui/PageHeader";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { SharedJob, sharedSpeech } from "../../features/invitations/SharedJob";
import { loadJobCatalog } from "../../features/jobs/catalog";
import { stagePath } from "../../features/jobs/JobStages";
import { ReadAloud } from "../../features/voice/ReadAloud";
import { LoadError, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";

const REASONS: invitationsApi.DeclineReason[] = ["not_available", "too_far", "not_my_work", "other"];

/** Worker: one invitation addressed to me — shared job details, read aloud, decline. */
export function WorkerInvitationPage() {
  const { id = "" } = useParams();
  const { t, language } = useI18n();
  const data = useLoad((signal) => Promise.all([invitationsApi.fetchInvitation(id, signal), loadJobCatalog(signal)]), [id]);
  const [reason, setReason] = useState<invitationsApi.DeclineReason[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [invitation, catalog] = data.state.data;

  async function decline() {
    setFailure(null);
    setBusy(true);
    try {
      data.set([await invitationsApi.declineInvitation(invitation.id, reason[0]), catalog]);
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  const tone = invitation.status === "active" ? "info" : "neutral";
  const booked = invitation.booking && invitation.booking.status !== "cancelled" ? invitation.booking : null;
  return (
    <div className="space-y-4">
      <PageHeader icon={<Inbox className="size-6" aria-hidden />} title={t("inv.title")}>
        <StatusBadge tone={tone}>{t(`inv.status.${invitation.status}`)}</StatusBadge>
      </PageHeader>
      {invitation.status === "withdrawn" && <Alert tone="warning">{t("inv.withdrawnNote")}</Alert>}
      {invitation.status === "declined" && <Alert tone="info" title={t("inv.declinedNote")}>{invitation.decline_reason ? t(`inv.reason.${invitation.decline_reason}`) : null}</Alert>}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)]">
        {/* Task, area, time and Listen together; the next action beside them. */}
        <div className="min-w-0 space-y-2 lg:col-start-1 lg:row-start-1">
          <SharedJob job={invitation.job} catalog={catalog}
            listen={<ReadAloud text={sharedSpeech(invitation.job, catalog, language, t)} language={language} showText={false} />} />
          <p className="text-sm text-muted">{t("inv.privacyNote")}</p>
        </div>
        <aside aria-label={t("quote.nextAction")} className="min-w-0 space-y-3 lg:sticky lg:top-24 lg:col-start-2 lg:row-start-1">
          <div className="card-action space-y-2 p-4">
            {invitation.status === "active" && !booked && <p className="text-sm">{t("inv.activeNote")}</p>}
            {invitation.booking && (
              <ButtonLink to={stagePath.work(invitation.booking.id)} fullWidth icon={<CalendarCheck className="size-5" aria-hidden />}>
                {t("stage.openWork")} · {t(`booking.status.${invitation.booking.status}`)}
              </ButtonLink>
            )}
            <ButtonLink to={stagePath.chat(invitation.id)} variant={invitation.status === "active" && !invitation.booking ? "primary" : "secondary"} fullWidth
              icon={<MessagesSquare className="size-5" aria-hidden />}>
              {invitation.status === "active" ? t("conv.openWorker") : t("conv.view")}
            </ButtonLink>
          </div>
          {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
          {invitation.status === "active" && !invitation.booking && (
            <details className="card p-3 sm:px-4">
              <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold"><Ban className="size-5" aria-hidden />{t("inv.decline.heading")}</summary>
              <div className="mt-3 space-y-3">
                <IconTileGroup
                  label={t("inv.decline.reasonLabel")}
                  mode="single"
                  columns={1}
                  options={REASONS.map((value) => ({ value, label: t(`inv.reason.${value}`), icon: <Ban className="size-6" aria-hidden /> }))}
                  value={reason}
                  onChange={setReason}
                />
                <Button variant="danger" fullWidth loading={busy} loadingLabel={t("onboarding.saving")} icon={<Ban className="size-5" aria-hidden />} onClick={() => void decline()}>
                  {t("inv.decline.button")}
                </Button>
              </div>
            </details>
          )}
          <ButtonLink to={PATHS.worker} variant="ghost" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
            {t("verify.backToDashboard")}
          </ButtonLink>
        </aside>
      </div>
    </div>
  );
}
