import { CircleCheck, Pencil } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import * as jobsApi from "../../api/jobs";
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
      <StepHeader step={3} title={t("jobs.review.title")} />
      <JobSummary job={job} catalog={catalog} />

      <section aria-label={t("voice.readAloud")} className="space-y-2">
        <p className="text-sm text-muted">{t("jobs.review.readAloudNote")}</p>
        <ReadAloud text={speechText(job, catalog, language, t)} language={language} />
      </section>

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
      <div className="grid gap-2">
        <Button fullWidth disabled={!job.ready_to_confirm || busy} loading={busy} loadingLabel={t("onboarding.saving")} icon={<CircleCheck className="size-5" aria-hidden />} onClick={() => void confirm()}>
          {t("jobs.review.confirm")}
        </Button>
        <ButtonLink to={`/customer/requests/${job.id}/details`} variant="secondary" fullWidth icon={<Pencil className="size-5" aria-hidden />}>
          {t("jobs.review.edit")}
        </ButtonLink>
      </div>
    </div>
  );
}
