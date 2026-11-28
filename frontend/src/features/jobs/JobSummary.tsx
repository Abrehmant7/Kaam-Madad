import { Lock } from "lucide-react";
import type { ReactNode } from "react";

import type { JobRequest } from "../../api/jobs";
import { Ltr } from "../../components/Ltr";
import { StatusBadge } from "../../components/ui/StatusBadge";
import type { I18nContextValue } from "../../i18n/context";
import { useI18n } from "../../i18n/context";
import type { Language } from "../../i18n/types";
import { type JobCatalog, labeller } from "./catalog";
import { textDir, isolateLtr } from "./text";
import { languageName } from "./UrduDescription";
import { formatDate, formatTime } from "./time";

type T = I18nContextValue["t"];

/** "5:00 pm – 7:00 pm" etc. */
export function windowText(job: JobRequest, language: Language): { date: string; time: string } | null {
  const { window_start: start, window_end: end } = job.details;
  if (!start || !end) return null;
  return { date: formatDate(start, language), time: `${formatTime(start, language)} – ${formatTime(end, language)}` };
}

/**
 * The text that may be read aloud: confirmed task, service area, date and time ONLY.
 * The private address, access notes, budget and original recording are never included.
 */
export function speechText(job: JobRequest, catalog: JobCatalog, language: Language, t: T): string {
  const label = labeller(catalog, language);
  const services = job.details.services.map(label.service).join(language === "ur" ? "، " : ", ");
  const when = windowText(job, language);
  const parts = [
    t("jobs.speech.task", { trade: label.trade(job.details.trade), services }),
    t("jobs.speech.area", { area: label.area(job.details.area), city: label.city(job.details.city) }),
  ];
  if (when) parts.push(t("jobs.speech.when", { date: when.date, time: isolateLtr(when.time) }));
  return parts.join(" ");
}

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{children}</dd>
    </div>
  );
}

/** Plain-language summary of a request (review and detail pages). */
export function JobSummary({ job, catalog }: { job: JobRequest; catalog: JobCatalog }) {
  const { t, language } = useI18n();
  const label = labeller(catalog, language);
  const separator = language === "ur" ? "، " : ", ";
  const when = windowText(job, language);
  const d = job.details;

  return (
    <div className="space-y-4">
      <dl className="space-y-3 card p-4">
        <Row title={t("jobs.summary.task")}>
          {label.trade(d.trade) || "—"}
          {d.services.length > 0 && `: ${d.services.map(label.service).join(separator)}`}
        </Row>
        {d.services_excluded.length > 0 && <Row title={t("jobs.summary.notNeeded")}>{d.services_excluded.map(label.service).join(separator)}</Row>}
        <Row title={t("jobs.summary.description")}>
          <span dir={textDir(d.description)} className="block whitespace-pre-line font-normal">{d.description || "—"}</span>
        </Row>
        {(job.urdu.needed || job.urdu.text) && (
          <Row title={t("jobs.urdu.heading")}>
            <span className="flex flex-col gap-1">
              <StatusBadge tone={job.urdu.status === "approved" ? "success" : job.urdu.status === "outdated" ? "danger" : "warning"}>
                {t(`jobs.urdu.status.${job.urdu.status}`)}
              </StatusBadge>
              {job.urdu.text && <span dir="rtl" lang="ur" className="block whitespace-pre-line font-normal">{job.urdu.text}</span>}
              {job.urdu.status !== "approved" && (
                <span className="text-sm font-normal text-muted">{t("jobs.urdu.notApproved", { language: languageName(job.urdu.description_language, t) })}</span>
              )}
            </span>
          </Row>
        )}
        <Row title={t("jobs.summary.area")}>{d.area ? `${label.area(d.area)}${separator}${label.city(d.city)}` : "—"}</Row>
        <Row title={t("jobs.summary.when")}>
          {when ? (
            <span className="flex flex-col">
              <span>{when.date}</span>
              <Ltr className="self-start">{when.time}</Ltr>
              <span className="text-sm font-normal text-muted">{t("jobs.time.zoneNote")}</span>
            </span>
          ) : (
            "—"
          )}
        </Row>
        {d.preferred_time_text && (
          <Row title={t("jobs.summary.youSaid")}>
            <span dir={textDir(d.preferred_time_text)} className="font-normal">“{d.preferred_time_text}”</span>
          </Row>
        )}
        {d.budget_pkr && (
          <Row title={t("jobs.summary.budget")}>
            <span className="flex flex-wrap items-center gap-1.5">
              <Ltr>PKR {Number(d.budget_pkr).toLocaleString("en-PK")}</Ltr>
              <span className="text-sm font-normal text-muted">{t("jobs.budget.note")}</span>
            </span>
          </Row>
        )}
        <Row title={t("jobs.summary.photos")}>{t("jobs.summary.photoCount", { count: job.photos.length })}</Row>
      </dl>

      {(d.address_private || d.access_notes) && (
        <section aria-labelledby="private-heading" className="space-y-2 rounded-2xl border border-dashed border-line bg-surface p-4">
          <h3 id="private-heading" className="flex items-center gap-2 font-bold">
            <Lock className="size-4" aria-hidden />
            {t("jobs.private.heading")}
          </h3>
          <p className="text-sm text-muted">{t("jobs.private.note")}</p>
          <dl className="space-y-2">
            {d.address_private && <Row title={t("jobs.field.address")}><span dir={textDir(d.address_private)} className="block font-normal">{d.address_private}</span></Row>}
            {d.access_notes && <Row title={t("jobs.field.access")}><span dir={textDir(d.access_notes)} className="block font-normal">{d.access_notes}</span></Row>}
          </dl>
        </section>
      )}
    </div>
  );
}

/** The untouched original input (typed text or transcript), with how it was given. */
export function OriginalInput({ job }: { job: JobRequest }) {
  const { t } = useI18n();
  if (!job.source.original_text) return null;
  return (
    <section aria-labelledby="original-heading" className="space-y-2 card p-4">
      <h3 id="original-heading" className="flex flex-wrap items-center gap-2 font-bold">
        {t("jobs.original.heading")}
        <StatusBadge tone="neutral">{job.source.kind === "voice" ? t("jobs.original.voice") : t("jobs.original.typed")}</StatusBadge>
      </h3>
      <blockquote dir={textDir(job.source.original_text)} className="whitespace-pre-line">{job.source.original_text}</blockquote>
      <p className="text-sm text-muted">{t("jobs.original.note")}</p>
    </section>
  );
}
