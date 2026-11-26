import type { ReactNode } from "react";

import type { SharedSummary } from "../../api/invitations";
import { Ltr } from "../../components/Ltr";
import type { I18nContextValue } from "../../i18n/context";
import { useI18n } from "../../i18n/context";
import type { Language } from "../../i18n/types";
import { type JobCatalog, labeller } from "../jobs/catalog";
import { isolateLtr, textDir } from "../jobs/text";
import { formatDate, formatTime } from "../jobs/time";

type T = I18nContextValue["t"];

/** Read-aloud text from SHAREABLE fields only: work, area, requested date and time. */
export function sharedSpeech(job: SharedSummary, catalog: JobCatalog, language: Language, t: T): string {
  const label = labeller(catalog, language);
  const services = job.services.map(label.service).join(language === "ur" ? "، " : ", ");
  const time = `${formatTime(job.window_start, language)} – ${formatTime(job.window_end, language)}`;
  return [
    t("jobs.speech.task", { trade: label.trade(job.trade), services }),
    t("jobs.speech.area", { area: label.area(job.area), city: label.city(job.city) }),
    t("jobs.speech.when", { date: formatDate(job.window_start, language), time: isolateLtr(time) }),
  ].join(" ");
}

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{children}</dd>
    </div>
  );
}

/** The shared view of a request (invitation preview for customers, invitation detail for workers). */
export function SharedJob({ job, catalog, showDescription = true }: { job: SharedSummary; catalog: JobCatalog; showDescription?: boolean }) {
  const { t, language } = useI18n();
  const label = labeller(catalog, language);
  const separator = language === "ur" ? "، " : ", ";
  return (
    <dl className="space-y-3 rounded-2xl border border-line bg-white p-4">
      <Row title={t("jobs.summary.task")}>
        {label.trade(job.trade)}: {job.services.map(label.service).join(separator)}
      </Row>
      {job.services_excluded.length > 0 && <Row title={t("jobs.summary.notNeeded")}>{job.services_excluded.map(label.service).join(separator)}</Row>}
      <Row title={t("jobs.summary.area")}>{`${label.area(job.area)}${separator}${label.city(job.city)}`}</Row>
      <Row title={t("rec.requestedTime")}>
        <span className="flex flex-col">
          <span>{formatDate(job.window_start, language)}</span>
          <Ltr className="self-start">{`${formatTime(job.window_start, language)} – ${formatTime(job.window_end, language)}`}</Ltr>
          <span className="text-sm font-normal text-muted">{t("rec.requestedTimeNote")}</span>
        </span>
      </Row>
      {showDescription && (
        <Row title={t("jobs.summary.description")}>
          <span dir={textDir(job.description)} className="block whitespace-pre-line font-normal">{job.description || "—"}</span>
        </Row>
      )}
      {job.budget_preference_pkr && (
        <Row title={t("rec.budgetPreference")}>
          <span className="flex flex-wrap items-center gap-1.5">
            <Ltr>PKR {Number(job.budget_preference_pkr).toLocaleString("en-PK")}</Ltr>
            <span className="text-sm font-normal text-muted">{t("jobs.budget.note")}</span>
          </span>
        </Row>
      )}
    </dl>
  );
}
