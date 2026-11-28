import { Award } from "lucide-react";

import * as bookingsApi from "../../api/bookings";
import { useI18n } from "../../i18n/context";
import { labeller, loadJobCatalog } from "../jobs/catalog";
import { textDir } from "../jobs/text";
import { formatDate } from "../jobs/time";
import { LoadError, useLoad } from "../worker/shared";
import { Stars } from "./ReviewPanel";

/** Worker dashboard (REV-02): completed jobs, rating with count, and feedback per job. No addresses or identities. */
export function WorkerFeedback() {
  const { t, language } = useI18n();
  const data = useLoad((signal) => Promise.all([bookingsApi.fetchFeedback(signal), loadJobCatalog(signal)]), []);
  if (data.state.status === "loading") return null;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [feedback, catalog] = data.state.data;
  const label = labeller(catalog, language);

  return (
    <section aria-labelledby="feedback-heading" className="space-y-3 card p-4">
      <h2 id="feedback-heading" className="flex items-center gap-2 text-lg font-bold">
        <Award className="size-6 text-primary" aria-hidden />
        {t("feedback.heading")}
      </h2>
      <dl className="grid grid-cols-2 gap-2 text-center">
        <div className="rounded-xl bg-surface p-3">
          <dt className="text-sm text-muted">{t("feedback.completed")}</dt>
          <dd className="text-2xl font-bold">{feedback.completed_jobs}</dd>
        </div>
        <div className="rounded-xl bg-surface p-3">
          <dt className="text-sm text-muted">{t("feedback.rating")}</dt>
          <dd className="font-bold">
            {feedback.average_rating !== null ? (
              <span className="flex flex-col items-center">
                <span className="text-2xl" dir="ltr">{feedback.average_rating}</span>
                <span className="text-sm font-normal">{t("feedback.reviewCount", { count: feedback.review_count })}</span>
              </span>
            ) : (
              <span className="text-sm font-normal text-muted">{t("rec.noReviews")}</span>
            )}
          </dd>
        </div>
      </dl>
      {feedback.completed_jobs === 0 ? (
        <p className="text-sm text-muted">{t("feedback.none")}</p>
      ) : (
        <ul className="space-y-2">
          {feedback.jobs.map((job) => (
            <li key={job.booking_id} className="space-y-1 rounded-xl border border-line p-3 text-sm">
              <p className="font-bold">
                {label.trade(job.trade)}: {job.services.map((code) => label.service(code)).join(language === "ur" ? "، " : ", ")}
              </p>
              <p className="text-muted">{label.area(job.area)} · {formatDate(job.completed_at, language)}</p>
              {job.review ? (
                <>
                  <Stars rating={job.review.rating} />
                  {job.review.text && <p dir={textDir(job.review.text)}>“{job.review.text}”</p>}
                </>
              ) : (
                <p className="text-muted">{t("feedback.noReviewForJob")}</p>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">{t("feedback.note")}</p>
    </section>
  );
}
