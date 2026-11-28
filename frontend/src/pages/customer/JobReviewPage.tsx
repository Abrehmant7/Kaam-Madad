import { CircleCheck, Eye, Pencil } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import type { SharedSummary } from "../../api/invitations";
import * as jobsApi from "../../api/jobs";
import { SharedJob } from "../../features/invitations/SharedJob";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { type JobCatalog, loadJobCatalog } from "../../features/jobs/catalog";
import { JobSummary, speechText } from "../../features/jobs/JobSummary";
import { ReadAloud } from "../../features/voice/ReadAloud";
import { LoadError, StepHeader, useLoad } from "../../features/worker/shared";
import { isTranslationKey, useI18n } from "../../i18n/context";
import { describeError, fieldErrorText } from "../../i18n/errors";

/** Step 3 — plain-language summary, read aloud, confirm. Confirming saves; it invites nobody. */
export function JobReviewPage() {
  const { id = "" } = useParams();
  const data = useLoad((signal) => Promise.all([jobsApi.fetchJob(id, signal), loadJobCatalog(signal)]), [id]);
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [job, catalog] = data.state.data;
  if (job.status !== "draft") return <Navigate to={`/customer/requests/${job.id}`} replace />;
  return <Review job={job} catalog={catalog} onReload={data.retry} />;
}

/** Exactly the shareable fields the server sends with an invitation (apps.jobs.summary.matching_summary). */
function workerPreview(job: jobsApi.JobRequest): SharedSummary | null {
  const d = job.details;
  if (!d.trade || !d.city || !d.area || !d.window_start || !d.window_end) return null;
  return {
    description: d.description, description_language: job.urdu.description_language,
    description_ur: job.urdu.status === "approved" ? job.urdu.text : null,
    trade: d.trade, services: d.services, services_excluded: d.services_excluded, city: d.city, area: d.area,
    window_start: d.window_start, window_end: d.window_end, budget_preference_pkr: d.budget_pkr, has_photos: job.photos.length > 0,
  };
}

function Review({ job, catalog, onReload }: { job: jobsApi.JobRequest; catalog: JobCatalog; onReload: () => void }) {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const issues = Object.entries(job.issues);
  const fieldName = (name: string) => {
    const key = `jobs.field.${name === "window_start" || name === "window_end" ? "when" : name}`;
    return isTranslationKey(key) ? t(key) : name;
  };

  async function confirm() {
    setFailure(null);
    setBusy(true);
    try {
      await jobsApi.confirmJob(job.id);
      navigate(`/customer/requests/${job.id}?confirmed=1`, { replace: true });
    } catch (error) {
      setFailure(error);
      onReload(); // show the server's current issues; the draft itself is unchanged
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <StepHeader step={3} flow="request" title={t("jobs.review.title")} />
      <div className="grid items-start gap-5 xl:grid-cols-2">
      <div className="min-w-0 space-y-4">
      <JobSummary job={job} catalog={catalog} />
      <section aria-label={t("voice.readAloud")} className="space-y-2">
        <p className="text-sm text-muted">{t("jobs.review.readAloudNote")}</p>
        <ReadAloud text={speechText(job, catalog, language, t)} language={language} />
      </section>
      </div>
      <div className="min-w-0 space-y-4">

      {(() => {
        const preview = workerPreview(job);
        if (!preview) return null;
        return (
          <section aria-labelledby="worker-sees-heading" className="space-y-2">
            <h2 id="worker-sees-heading" className="flex items-center gap-2 text-lg font-bold">
              <Eye className="size-5 text-primary" aria-hidden />
              {t("jobs.review.workerSees")}
            </h2>
            <p className="text-sm text-muted">{t("jobs.review.workerSeesNote")}</p>
            <SharedJob job={preview} catalog={catalog} preview />
          </section>
        );
      })()}

      </div>
      </div>

      {issues.length > 0 && (
        <Alert tone="warning" title={t("jobs.review.notReady")}>
          <ul className="list-inside list-disc">
            {issues.map(([name, codes]) => (
              <li key={name}>
                {fieldName(name)}: {codes.map((code) => fieldErrorText(code, t)).join(" ")}
              </li>
            ))}
          </ul>
        </Alert>
      )}
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      <Alert tone="info">{t("jobs.review.meaning")}</Alert>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button className="sm:min-w-56" disabled={!job.ready_to_confirm || busy} loading={busy} loadingLabel={t("onboarding.saving")} icon={<CircleCheck className="size-5" aria-hidden />} onClick={() => void confirm()}>
          {t("jobs.review.confirm")}
        </Button>
        <ButtonLink to={`/customer/requests/${job.id}/details`} variant="secondary" icon={<Pencil className="size-5" aria-hidden />}>
          {t("jobs.review.edit")}
        </ButtonLink>
      </div>
    </div>
  );
}
