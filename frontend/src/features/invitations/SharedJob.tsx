import type { ReactNode } from "react";

import type { SharedSummary } from "../../api/invitations";
import { Ltr } from "../../components/Ltr";
import type { I18nContextValue } from "../../i18n/context";
import { useI18n } from "../../i18n/context";
import type { Language } from "../../i18n/types";
import { type JobCatalog, labeller } from "../jobs/catalog";
import { isolateLtr, textDir } from "../jobs/text";
import { languageName } from "../jobs/UrduDescription";
import { formatDate, formatTime } from "../jobs/time";

type T = I18nContextValue["t"];

/** Language of the customer's own words (older invitations carry no ``description_language``: judged by script). */
function originalLanguage(job: SharedSummary): "ur" | "en" | "mixed" | null {
  if (job.description_language) return job.description_language;
  const dir = textDir(job.description);
  return dir === "rtl" ? "ur" : dir === "ltr" ? "en" : null;
}

/**
 * The description to read to someone using ``language``, or null when none is in their language:
 * - Urdu: the customer-approved Urdu version first; otherwise the original when it is already in Urdu.
 * - English: the original when it is in English.
 * An untranslated English request read in Urdu falls back to the structured details only.
 */
export function spokenDescription(job: SharedSummary, language: Language): string | null {
  const original = originalLanguage(job);
  const text = language === "ur" ? (job.description_ur || (original === "ur" ? job.description : "")) : original === "en" ? job.description : "";
  return text.trim() ? text.trim().slice(0, 800) : null;
}

/**
 * Read-aloud text from SHAREABLE fields only: work, the approved description in the reader's language, area,
 * requested date and time. Never the address, access notes, photos, recording or unapproved text.
 */
export function sharedSpeech(job: SharedSummary, catalog: JobCatalog, language: Language, t: T): string {
  const label = labeller(catalog, language);
  const services = job.services.map(label.service).join(language === "ur" ? "، " : ", ");
  const time = `${formatTime(job.window_start, language)} – ${formatTime(job.window_end, language)}`;
  const parts = [t("jobs.speech.task", { trade: label.trade(job.trade), services })];
  const description = spokenDescription(job, language);
  if (description) parts.push(t("jobs.speech.description", { text: description }));
  parts.push(
    t("jobs.speech.area", { area: label.area(job.area), city: label.city(job.city) }),
    t("jobs.speech.when", { date: formatDate(job.window_start, language), time: isolateLtr(time) }),
  );
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

/**
 * The shared view of a request (invitation preview for customers, invitation detail for workers). ``listen`` is
 * placed right after the task, area and time, so the Listen control stays with them. ``preview`` (customer) always
 * shows the approved Urdu version, whatever the customer's own interface language.
 */
export function SharedJob({ job, catalog, showDescription = true, listen, preview = false, plain = false }: {
  job: SharedSummary; catalog: JobCatalog; showDescription?: boolean; listen?: ReactNode; preview?: boolean;
  /** Without the card frame (inside another card). */
  plain?: boolean;
}) {
  const { t, language } = useI18n();
  const label = labeller(catalog, language);
  const separator = language === "ur" ? "، " : ", ";
  return (
    <dl className={plain ? "space-y-3" : "space-y-3 card p-4"}>
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
      {listen && <div className="border-t border-line pt-3">{listen}</div>}
      {showDescription && (language === "ur" || preview) && job.description_ur && (
        <Row title={t("jobs.summary.descriptionUr")}>
          <span dir="rtl" lang="ur" className="block whitespace-pre-line font-normal">{job.description_ur}</span>
        </Row>
      )}
      {showDescription && (
        <Row title={job.description_language && job.description_language !== "ur"
          ? t("jobs.summary.originalWords", { language: languageName(job.description_language, t) })
          : t("jobs.summary.description")}>
          <span dir={textDir(job.description)} lang={job.description_language === "en" ? "en" : undefined}
            className="block whitespace-pre-line font-normal">{job.description || "—"}</span>
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
