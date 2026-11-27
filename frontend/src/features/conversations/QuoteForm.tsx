import { Save, Send, Trash2 } from "lucide-react";
import { useState } from "react";

import * as convApi from "../../api/conversations";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, fieldErrorText } from "../../i18n/errors";
import { money } from "./quoteText";
import { TermsFields, useTerms } from "./TermsFields";

/** The worker's structured quote. The server validates, computes totals and freezes each submitted version. */
export function QuoteForm({ invitationId, start, onDone }: { invitationId: string; start: convApi.Quote | null; onDone: () => void }) {
  const { t } = useI18n();
  const state = useTerms(start);
  const [saved, setSaved] = useState<convApi.Quote | null>(start?.status === "draft" ? start : null);
  const [busy, setBusy] = useState<"save" | "submit" | "discard" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [codes, setCodes] = useState<Record<string, string[]>>({});

  const issues = { ...(saved?.issues ?? {}), ...codes };
  const errors = (name: string) => (issues[name] ?? []).map((code) => fieldErrorText(code, t));

  async function run(kind: NonNullable<typeof busy>) {
    setFailure(null);
    setCodes({});
    setBusy(kind);
    try {
      if (kind === "discard") {
        await convApi.deleteDraft(invitationId);
        onDone();
        return;
      }
      const draft = await convApi.saveDraft(invitationId, state.terms());
      setSaved(draft);
      if (kind === "submit") {
        await convApi.submitDraft(invitationId);
        onDone();
      }
    } catch (error) {
      setCodes(fieldErrorCodes(error));
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="quote-form-heading" className="space-y-4 rounded-2xl border-2 border-primary/40 bg-white p-4">
      <h3 id="quote-form-heading" className="text-lg font-bold">{t("quote.form.title")}</h3>
      <p className="text-sm text-muted">{t("quote.form.intro")}</p>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      <TermsFields state={state} errors={errors} />

      {saved?.totals && (
        <p className="rounded-xl bg-surface p-3 font-bold">
          {t("quote.field.total")}: <bdi dir="ltr">{money(saved.totals.known_total)}</bdi>
          {!saved.totals.complete && <span className="font-normal"> {t("quote.plusUnknown")}</span>}
        </p>
      )}
      <p className="text-sm text-muted">{t("quote.form.submitNote")}</p>
      <div className="grid gap-2">
        <Button fullWidth loading={busy === "submit"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Send className="size-5" aria-hidden />} onClick={() => void run("submit")}>
          {t("quote.form.submit")}
        </Button>
        <Button variant="secondary" fullWidth loading={busy === "save"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Save className="size-5" aria-hidden />} onClick={() => void run("save")}>
          {t("quote.form.saveDraft")}
        </Button>
        {saved && (
          <Button variant="ghost" disabled={busy !== null} icon={<Trash2 className="size-5" aria-hidden />} onClick={() => void run("discard")}>
            {t("quote.form.discard")}
          </Button>
        )}
      </div>
    </section>
  );
}
