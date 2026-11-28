import { CircleCheck, Mic, RefreshCw, Sparkles, Undo2 } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import type { Materials } from "../../api/conversations";
import * as voiceApi from "../../api/voice";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError, LocalMessage } from "../../i18n/errors";
import type { TranslationKey } from "../../i18n/types";
import { textDir } from "../jobs/text";
import { formatDate, toIso } from "../jobs/time";
import { SimulatedBadge } from "../voice/SimulatedBadge";
import { type CapturedAudio, VoiceCapture } from "../voice/VoiceCapture";
import { money } from "./quoteText";
import type { TermsState } from "./TermsFields";

type Busy = "uploading" | "transcribing" | "interpreting" | null;
type Key = "scope" | "labour" | "basis" | "quantity" | "materials" | "materialsAmount" | "date" | "startTime" | "endTime";
const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };

const LABELS: Record<Key, TranslationKey> = {
  scope: "quote.field.scope", labour: "quote.form.labourAmount", basis: "quote.form.basis", quantity: "quote.field.quantity",
  materials: "quote.field.materials", materialsAmount: "quote.form.materialsAmount", date: "jobs.field.date",
  startTime: "jobs.field.startTime", endTime: "jobs.field.endTime",
};
/** Server field names (draft.uncertain / draft.heard) → form fields. */
const FROM_SERVER: Record<string, Key> = {
  scope: "scope", labour_amount: "labour", labour_basis: "basis", quantity: "quantity", materials: "materials",
  materials_amount: "materialsAmount", date: "date", start_time: "startTime", end_time: "endTime",
};

/** The suggested values, as the form stores them (strings). Only what the worker clearly said is present. */
function suggested(fields: voiceApi.DraftFields): Partial<Record<Key, string>> {
  const out: Partial<Record<Key, string>> = {};
  if (fields.scope) out.scope = fields.scope;
  if (fields.labour_amount != null) out.labour = String(fields.labour_amount);
  if (fields.labour_basis) out.basis = fields.labour_basis;
  if (fields.quantity != null) out.quantity = String(fields.quantity);
  if (fields.materials) out.materials = fields.materials;
  if (fields.materials_amount != null) out.materialsAmount = String(fields.materials_amount);
  if (fields.date) out.date = fields.date;
  if (fields.start_time) out.startTime = fields.start_time;
  if (fields.end_time) out.endTime = fields.end_time;
  return out;
}

type Outcome = "filled" | "same" | "kept";

/**
 * Optional "Answer by voice" for the worker's quote: record or upload → speech-to-text → quote suggestions → the form.
 * Only clearly stated terms are suggested. An empty field is filled in; a field the worker already typed is kept, and
 * the different suggestion waits for an explicit "Use". Everything stays editable in the form below, and nothing is
 * sent: the worker still presses "Send quote" (the server validates the terms and calculates the totals). A failure
 * changes nothing that was typed.
 */
export function QuoteVoice({ state }: { state: TermsState }) {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const f = state.fields;
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [result, setResult] = useState<{ heard: string; simulated: boolean; values: Partial<Record<Key, string>>; outcome: Partial<Record<Key, Outcome>>;
    unclear: Key[]; heardPhrases: Record<string, string> } | null>(null);

  const current: Record<Key, string> = {
    scope: f.scope.trim(), labour: f.labour.trim(), basis: f.labour.trim() ? f.basis[0] ?? "" : "", quantity: f.quantity.trim(),
    materials: f.materials[0] ?? "", materialsAmount: f.materialsAmount.trim(), date: f.date, startTime: f.startTime, endTime: f.endTime,
  };
  // The latest typed values: the worker may keep typing while the voice answer is processed.
  const latest = useRef(current);
  latest.current = current;
  function apply(key: Key, value: string) {
    const set: Record<Key, (v: string) => void> = {
      scope: f.setScope, labour: f.setLabour, basis: (v) => f.setBasis([v as "total" | "per_item"]), quantity: f.setQuantity,
      materials: (v) => f.setMaterials([v as Materials]), materialsAmount: f.setMaterialsAmount,
      date: f.setDate, startTime: f.setStartTime, endTime: f.setEndTime,
    };
    set[key](value);
  }

  const onAudio = useCallback((next: CapturedAudio | null) => {
    setAudio(next);
    setResult(null);
    setFailure(null);
  }, []);

  async function run() {
    if (!audio) return;
    setFailure(null);
    setResult(null);
    try {
      setBusy("uploading");
      const clip = await voiceApi.uploadClip(audio.blob, audio.filename, "quote_terms", audio.source);
      setBusy("transcribing");
      const transcription = await voiceApi.transcribe(clip.id, language);
      if (transcription.no_speech || !transcription.text.trim()) throw new LocalMessage("voiceAnswer.noSpeech");
      setBusy("interpreting");
      const interpretation = await voiceApi.interpretTranscription("quote_terms", transcription.id, transcription.language);
      const values = suggested(interpretation.effective_fields);
      const outcome: Partial<Record<Key, Outcome>> = {};
      (Object.keys(values) as Key[]).forEach((key) => {
        const value = values[key] ?? "";
        const typed = latest.current[key];
        if (!typed) {
          apply(key, value);
          outcome[key] = "filled";
        } else {
          outcome[key] = typed === value ? "same" : "kept"; // never overwrite what the worker typed
        }
      });
      const unclear = interpretation.draft.uncertain.map((name) => FROM_SERVER[name]).filter((key): key is Key => Boolean(key) && !values[key as Key]);
      setResult({ heard: transcription.text, simulated: transcription.simulated || interpretation.simulated, values, outcome,
        unclear: [...new Set(unclear)], heardPhrases: interpretation.draft.heard });
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  const show = (key: Key, value: string): string => {
    if (key === "labour" || key === "materialsAmount") return money(value) ?? value;
    if (key === "materials") return t(`quote.materials.${value}` as TranslationKey);
    if (key === "basis") return t(`quote.basis.${value}` as TranslationKey);
    if (key === "date") return formatDate(toIso(value, "12:00"), language);
    return value;
  };
  const join = (items: string[]) => items.join(language === "ur" ? "، " : ", ");
  const needed: Key[] = [
    ...(["scope"] as Key[]),
    ...(state.inspectionOnly ? [] : (["labour", "materials"] as Key[])),
    ...(!state.inspectionOnly && f.basis[0] === "per_item" ? (["quantity"] as Key[]) : []),
    ...(["date", "startTime", "endTime"] as Key[]),
  ].filter((key) => !current[key]);

  return (
    <details className="group rounded-2xl border border-primary/30 bg-primary-soft/40 p-3 sm:p-4">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 font-bold text-primary">
        <span className="grid size-9 place-items-center rounded-full bg-white"><Mic className="size-5" aria-hidden /></span>
        {t("voiceAnswer.open")}
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-sm">{t("quoteVoice.intro")}</p>
        <VoiceCapture audio={audio} onAudio={onAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={busy !== null} />
        <Button disabled={!audio || busy !== null} loading={busy !== null} loadingLabel={busy ? t(`voiceAnswer.busy.${busy}`) : undefined}
          icon={<Sparkles className="size-5" aria-hidden />} onClick={() => void run()}>
          {t("quoteVoice.fill")}
        </Button>
        {failure !== null && (
          <Alert tone="warning" title={t("quoteVoice.failed")}>
            <p>{describeError(failure, t)}</p>
            <p className="text-sm">{t("quoteVoice.keptTyped")}</p>
            <Button variant="secondary" className="mt-2" icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => void run()}>
              {t("common.retry")}
            </Button>
          </Alert>
        )}
        {result && (
          <section aria-label={t("quoteVoice.suggestions")} className="space-y-2" role="status">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold">{t("voiceAnswer.heard")}</span>
              <SimulatedBadge show={result.simulated} />
            </div>
            <blockquote dir={textDir(result.heard)} className="rounded-xl border border-line bg-white p-3">{result.heard}</blockquote>
            {Object.keys(result.values).length === 0 ? (
              <Alert tone="info">{t("quoteVoice.none")}</Alert>
            ) : (
              <ul className="space-y-1.5">
                {(Object.keys(result.values) as Key[]).map((key) => {
                  const value = result.values[key] ?? "";
                  const outcome = result.outcome[key];
                  return (
                    <li key={key} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-white p-2 text-sm">
                      <span className="text-muted">{t(LABELS[key])}:</span>
                      <bdi className="font-bold" dir={key === "scope" ? textDir(value) : undefined}>{show(key, value)}</bdi>
                      {outcome === "filled" && <span className="inline-flex items-center gap-1 text-success-strong"><CircleCheck className="size-4" aria-hidden />{t("quoteVoice.filled")}</span>}
                      {outcome === "same" && <span className="text-muted">{t("quoteVoice.same")}</span>}
                      {outcome === "kept" && (
                        <>
                          <span className="text-warning-strong">{t("quoteVoice.kept", { value: show(key, current[key]) })}</span>
                          <Button variant="ghost" className="min-h-11 px-1" icon={<Undo2 className="size-4" aria-hidden />}
                            onClick={() => { apply(key, value); setResult({ ...result, outcome: { ...result.outcome, [key]: "filled" } }); }}>
                            {t("quoteVoice.use", { value: show(key, value) })}
                          </Button>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {result.unclear.length > 0 && (
              <p className="text-sm font-bold text-warning-strong">
                {t("quoteVoice.unclear", { fields: join(result.unclear.map((key) => t(LABELS[key]))) })}
              </p>
            )}
            {needed.length > 0 && <p className="text-sm">{t("quoteVoice.stillNeeded", { fields: join(needed.map((key) => t(LABELS[key]))) })}</p>}
            <p className="text-sm text-muted">{t("quoteVoice.check")}</p>
          </section>
        )}
      </div>
    </details>
  );
}
