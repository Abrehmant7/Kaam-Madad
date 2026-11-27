import { Languages } from "lucide-react";

import type { UrduDescription } from "../../api/jobs";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { useI18n } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/types";

export const MAX_URDU_DESCRIPTION = 800;

/** "English" / "انگریزی" etc. for a description language code. */
export function languageName(code: string | null | undefined, t: (key: TranslationKey) => string): string {
  return code === "en" || code === "mixed" || code === "ur" ? t(`jobs.language.${code}`) : t("jobs.language.en");
}

const STATUS_TONE = { none: "neutral", suggested: "warning", approved: "success", outdated: "danger" } as const;

/**
 * The customer reviews, edits and approves the Urdu version of an English / Roman Urdu / mixed description.
 * Editing the text withdraws an approval (the server re-checks); only an approved version is shared with workers.
 */
export function UrduDescriptionEditor({ urdu, text, approved, onText, onApproved, errors }: {
  urdu: UrduDescription;
  text: string;
  approved: boolean;
  onText: (value: string) => void;
  onApproved: (value: boolean) => void;
  errors?: string[];
}) {
  const { t } = useI18n();
  const status = approved && text.trim() ? "approved" : text !== urdu.text || urdu.status === "approved" ? "suggested" : urdu.status;
  const language = languageName(urdu.description_language, t);
  return (
    <section aria-labelledby="urdu-heading" className="space-y-3 rounded-2xl border-2 border-primary/40 bg-white p-4">
      <h2 id="urdu-heading" className="flex flex-wrap items-center gap-2 font-bold">
        <Languages className="size-5" aria-hidden />
        {t("jobs.urdu.heading")}
        <StatusBadge tone={STATUS_TONE[status]}>{t(`jobs.urdu.status.${status}`)}</StatusBadge>
      </h2>
      <p className="text-sm">{t("jobs.urdu.explain", { language })}</p>
      <TextArea
        label={t("jobs.urdu.label")}
        value={text}
        onChange={(value) => {
          onText(value);
          if (approved) onApproved(false);
        }}
        errors={errors}
        maxLength={MAX_URDU_DESCRIPTION}
        rows={4}
        dir="rtl"
        lang="ur"
      />
      <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border-2 border-line bg-surface p-3">
        <input type="checkbox" className="mt-1 size-6 shrink-0 accent-primary" checked={approved} disabled={!text.trim()}
          onChange={(event) => onApproved(event.target.checked)} />
        <span>{t("jobs.urdu.approve")}</span>
      </label>
      {!approved && <p className="text-sm text-muted">{t("jobs.urdu.notApproved", { language })}</p>}
    </section>
  );
}
