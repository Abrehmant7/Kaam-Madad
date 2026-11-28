import { ArrowLeft, CalendarCheck, Pencil, Users } from "lucide-react";
import { useSearchParams, useParams } from "react-router";

import * as jobsApi from "../../api/jobs";
import { PATHS } from "../../auth/paths";
import { Alert } from "../../components/ui/Alert";
import { ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { loadJobCatalog } from "../../features/jobs/catalog";
import { JobPhotos } from "../../features/jobs/JobPhotos";
import { JobSummary, OriginalInput, speechText } from "../../features/jobs/JobSummary";
import { isolateLtr } from "../../features/jobs/text";
import { formatDate, formatTime } from "../../features/jobs/time";
import { ReadAloud } from "../../features/voice/ReadAloud";
import { LoadError, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";

/** A saved request, reopened from "My requests". Confirmed requests are read-only in M5. */
export function JobDetailPage() {
  const { t, language } = useI18n();
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const data = useLoad((signal) => Promise.all([jobsApi.fetchJob(id, signal), loadJobCatalog(signal)]), [id]);
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [job, catalog] = data.state.data;
  const confirmed = job.status === "confirmed";

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("jobs.detail.title")}</h1>
        <StatusBadge tone={confirmed ? "success" : "neutral"}>{confirmed ? t("jobs.status.confirmed") : t("jobs.status.draft")}</StatusBadge>
      </div>

      {confirmed ? (
        <Alert tone="success" title={params.get("confirmed") ? t("jobs.detail.justConfirmed") : undefined}>
          <p>{t("jobs.detail.confirmedNoteM6")}</p>
          {job.confirmed_at && (
            <p className="text-sm">{t("jobs.detail.confirmedAt", { date: formatDate(job.confirmed_at, language), time: isolateLtr(formatTime(job.confirmed_at, language)) })}</p>
          )}
        </Alert>
      ) : (
        <Alert tone="warning">{t("jobs.detail.draftNote")}</Alert>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)]">
      <div className="min-w-0 space-y-4">
      <JobSummary job={job} catalog={catalog} />
      {confirmed && <ReadAloud text={speechText(job, catalog, language, t)} language={language} />}
      {job.photos.length > 0 && <JobPhotos jobId={job.id} photos={job.photos} editable={false} />}
      <OriginalInput job={job} />
      </div>

      <div className="grid gap-2 lg:sticky lg:top-24">
        {confirmed && job.booking && (
          <ButtonLink to={`/bookings/${job.booking.id}`} fullWidth icon={<CalendarCheck className="size-5" aria-hidden />}>
            {t("stage.openWork")} · {t(`booking.status.${job.booking.status}`)}
          </ButtonLink>
        )}
        {confirmed && !job.booking && (
          <ButtonLink to={`/customer/requests/${job.id}/workers`} fullWidth icon={<Users className="size-5" aria-hidden />}>
            {t("rec.cta")}
          </ButtonLink>
        )}
        {!confirmed && (
          <ButtonLink to={`/customer/requests/${job.id}/details`} fullWidth icon={<Pencil className="size-5" aria-hidden />}>
            {t("jobs.list.continue")}
          </ButtonLink>
        )}
        <ButtonLink to={PATHS.customer} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
          {t("jobs.detail.back")}
        </ButtonLink>
      </div>
      </div>
    </div>
  );
}
