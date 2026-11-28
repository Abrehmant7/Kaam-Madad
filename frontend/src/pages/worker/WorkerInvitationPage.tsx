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
  return (
    <div className="space-y-5">
      <PageHeader icon={<Inbox className="size-6" aria-hidden />} title={t("inv.title")}>
        <StatusBadge tone={tone}>{t(`inv.status.${invitation.status}`)}</StatusBadge>
      </PageHeader>
      {invitation.status === "active" && <Alert tone="info">{t("inv.activeNote")}</Alert>}
      {invitation.status === "withdrawn" && <Alert tone="warning">{t("inv.withdrawnNote")}</Alert>}
      {invitation.status === "declined" && <Alert tone="info" title={t("inv.declinedNote")}>{invitation.decline_reason ? t(`inv.reason.${invitation.decline_reason}`) : null}</Alert>}

      {/* Task, area, time and Listen together, then the next action. */}
      <SharedJob job={invitation.job} catalog={catalog}
        listen={<ReadAloud text={sharedSpeech(invitation.job, catalog, language, t)} language={language} showText={false} />} />
      <div className="grid gap-2">
        {invitation.booking && (
          <ButtonLink to={`/bookings/${invitation.booking.id}`} fullWidth icon={<CalendarCheck className="size-5" aria-hidden />}>
            {t("booking.open")} · {t(`booking.status.${invitation.booking.status}`)}
          </ButtonLink>
        )}
        <ButtonLink to={`/conversations/${invitation.id}`} variant={invitation.status === "active" && !invitation.booking ? "primary" : "secondary"} fullWidth
          icon={<MessagesSquare className="size-5" aria-hidden />}>
          {invitation.status === "active" ? t("conv.openWorker") : t("conv.view")}
        </ButtonLink>
      </div>
      <p className="text-sm text-muted">{t("inv.privacyNote")}</p>

      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      {invitation.status === "active" && !invitation.booking && (
        <section aria-labelledby="decline-heading" className="space-y-3 card p-4">
          <h2 id="decline-heading" className="font-bold">{t("inv.decline.heading")}</h2>
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
        </section>
      )}
      <p className="text-sm text-muted">{t("inv.nextNote")}</p>
      <ButtonLink to={PATHS.worker} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("verify.backToDashboard")}
      </ButtonLink>
    </div>
  );
}
