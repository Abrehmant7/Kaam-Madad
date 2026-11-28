import { Save, Send, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import * as convApi from "../../api/conversations";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, fieldErrorText } from "../../i18n/errors";
import { clearDraft, readDraft, writeDraft } from "../drafts";
import { money } from "./quoteText";
import { TermsFields, useTerms } from "./TermsFields";

/** In-memory key for the terms the worker is typing (kept while they check the chat and come back). */
export const quoteFormDraftKey = (invitationId: string) => `quote-form:${invitationId}`;

/** The worker's structured quote. The server validates, computes totals and freezes each submitted version. */
export function QuoteForm({ invitationId, start, onDone, onCancel }: {
  invitationId: string; start: convApi.Quote | null; onDone: () => void; onCancel?: () => void;
}) {
  const { t } = useI18n();
  const key = quoteFormDraftKey(invitationId);
  const state = useTerms(readDraft<convApi.QuoteTerms>(key) ?? start);
  const [saved, setSaved] = useState<convApi.Quote | null>(start?.status === "draft" ? start : null);
  const [busy, setBusy] = useState<"save" | "submit" | "discard" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [codes, setCodes] = useState<Record<string, string[]>>({});
  const finished = useRef(false);

  // What was typed is kept (in memory only) as it changes, so the chat can offer "Continue your draft" and the
  // form comes back as it was. Sending or discarding forgets it.
  const typed = JSON.stringify(state.terms());
  const initial = useRef(typed);
  useEffect(() => {
    if (!finished.current && typed !== initial.current) writeDraft(key, JSON.parse(typed) as convApi.QuoteTerms);
  }, [key, typed]);

  const issues = { ...(saved?.issues ?? {}), ...codes };
  const errors = (name: string) => (issues[name] ?? []).map((code) => fieldErrorText(code, t));

  function finish() {
    finished.current = true;
    clearDraft(key);
    onDone();
  }

  async function run(kind: NonNullable<typeof busy>) {
    setFailure(null);
    setCodes({});
    setBusy(kind);
    try {
      if (kind === "discard") {
        await convApi.deleteDraft(invitationId);
        finish();
        return;
      }
      const draft = await convApi.saveDraft(invitationId, state.terms());
      setSaved(draft);
      if (kind === "submit") {
        await convApi.submitDraft(invitationId);
        finish();
      }
    } catch (error) {
      setCodes(fieldErrorCodes(error));
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="quote-form-heading" className="space-y-4 card-action p-4 sm:p-5">
      <div className="space-y-1">
        <h2 id="quote-form-heading" className="text-lg font-bold">{t("quote.form.title")}</h2>
        <p className="text-sm text-muted">{t("quote.form.intro")}</p>
      </div>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      <TermsFields state={state} errors={errors} />

      {saved?.totals && (
        <p className="rounded-xl bg-surface p-3 font-bold">
          {t("quote.field.total")}: <bdi dir="ltr">{money(saved.totals.known_total)}</bdi>
          {!saved.totals.complete && <span className="font-normal"> {t("quote.plusUnknown")}</span>}
        </p>
      )}
      <p className="text-sm text-muted">{t("quote.form.submitNote")}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <Button className="sm:min-w-48" loading={busy === "submit"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Send className="size-5" aria-hidden />} onClick={() => void run("submit")}>
          {t("quote.form.submit")}
        </Button>
        <Button variant="secondary" loading={busy === "save"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Save className="size-5" aria-hidden />} onClick={() => void run("save")}>
          {t("quote.form.saveDraft")}
        </Button>
        {saved && (
          <Button variant="ghost" disabled={busy !== null} icon={<Trash2 className="size-5" aria-hidden />} onClick={() => void run("discard")}>
            {t("quote.form.discard")}
          </Button>
        )}
        {onCancel && (
          <Button variant="ghost" disabled={busy !== null} icon={<X className="size-5" aria-hidden />} onClick={onCancel}>
            {t("quote.form.close")}
          </Button>
        )}
      </div>
    </section>
  );
}
