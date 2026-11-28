import { ClipboardList } from "lucide-react";

import type { SharedSummary } from "../../api/invitations";
import { Ltr } from "../../components/Ltr";
import { useI18n } from "../../i18n/context";
import { SharedJob, sharedSpeech, spokenDescription } from "../invitations/SharedJob";
import { type JobCatalog, labeller } from "../jobs/catalog";
import { textDir } from "../jobs/text";
import { formatDate, formatTime } from "../jobs/time";
import { ReadAloud } from "../voice/ReadAloud";

/**
 * The request in a few lines (work, area, time, budget, the description in the reader's language) with Listen, and
 * the full shared request behind "View request details". Only shareable fields: never the address or photos.
 */
export function JobBrief({ job, catalog }: { job: SharedSummary; catalog: JobCatalog }) {
  const { t, language } = useI18n();
  const label = labeller(catalog, language);
  const separator = language === "ur" ? "، " : ", ";
  const description = spokenDescription(job, language) ?? job.description;
  return (
    <section aria-labelledby="job-brief-heading" className="card space-y-2 p-4">
      <h2 id="job-brief-heading" className="flex items-center gap-2 text-sm font-bold text-muted">
        <ClipboardList className="size-4" aria-hidden />
        {t("conv.brief")}
      </h2>
      <p className="font-bold">{label.trade(job.trade)}: {job.services.map(label.service).join(separator)}</p>
      <p className="flex flex-wrap gap-x-2 text-sm">
        <span>{`${label.area(job.area)}${separator}${label.city(job.city)}`}</span>
        <span>{formatDate(job.window_start, language)}</span>
        <Ltr>{`${formatTime(job.window_start, language)} – ${formatTime(job.window_end, language)}`}</Ltr>
      </p>
      {job.budget_preference_pkr && (
        <p className="text-sm max-lg:hidden">{t("rec.budgetPreference")}: <Ltr>PKR {Number(job.budget_preference_pkr).toLocaleString("en-PK")}</Ltr></p>
      )}
      {description && <p dir={textDir(description)} className="line-clamp-3 text-sm text-muted max-lg:hidden">{description}</p>}
      <ReadAloud text={sharedSpeech(job, catalog, language, t)} language={language} showText={false} />
      <details className="border-t border-line pt-1">
        <summary className="flex min-h-11 cursor-pointer items-center font-bold text-primary">{t("conv.viewRequest")}</summary>
        <div className="mt-2"><SharedJob job={job} catalog={catalog} plain /></div>
      </details>
    </section>
  );
}
