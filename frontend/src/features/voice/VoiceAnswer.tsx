import { CircleCheck, CircleDashed, LoaderCircle, Mic, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useState } from "react";

import * as voiceApi from "../../api/voice";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError, LocalMessage } from "../../i18n/errors";
import { textDir } from "../jobs/text";
import { SimulatedBadge } from "./SimulatedBadge";
import { type CapturedAudio, VoiceCapture } from "./VoiceCapture";

type Kind = "onboarding_work" | "onboarding_areas";
type Busy = "uploading" | "transcribing" | "interpreting" | null;
const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };

export interface VoiceSuggestion {
  fields: voiceApi.DraftFields;
  uncertain: string[];
  notSelected: string[];
  unmatched: string[];
}

function StepItem({ n, label, state }: { n: number; label: string; state: "done" | "current" | "pending" }) {
  const icon = state === "done" ? <CircleCheck className="size-5 text-success" aria-hidden />
    : state === "current" ? <span className="grid size-5 place-items-center rounded-full bg-primary font-sans text-[11px] font-bold text-white">{n}</span>
      : <CircleDashed className="size-5 text-muted" aria-hidden />;
  return (
    <li aria-current={state === "current" ? "step" : undefined} className={`flex items-center gap-2 text-sm ${state === "current" ? "font-bold text-primary" : "text-muted"}`}>
      {icon}
      <span>{label}</span>
    </li>
  );
}

/**
 * Optional "Answer by voice" for a worker signup screen, shown beside the manual choices. Three visible steps:
 * record or upload → we write it down (speech-to-text in the spoken language, then suggestions for THIS screen) →
 * check the choices. Suggestions fill the page's own editable choices; nothing is saved until the worker presses the
 * screen's Save button. A failure keeps the recording (try again) and leaves manual selection untouched.
 */
export function VoiceAnswer({ kind, onSuggest, describe }: {
  kind: Kind;
  onSuggest: (suggestion: VoiceSuggestion) => void;
  /** Localized labels for area codes (screen 3), to list the areas the worker said they do not go to. */
  describe?: (code: string) => string;
}) {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [result, setResult] = useState<{ heard: string; simulated: boolean; suggestion: VoiceSuggestion; empty: boolean } | null>(null);

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
      const clip = await voiceApi.uploadClip(audio.blob, audio.filename, kind, audio.source);
      setBusy("transcribing");
      const transcription = await voiceApi.transcribe(clip.id, language);
      if (transcription.no_speech || !transcription.text.trim()) throw new LocalMessage("voiceAnswer.noSpeech");
      setBusy("interpreting");
      const interpretation = await voiceApi.interpretTranscription(kind, transcription.id, transcription.language);
      const fields = interpretation.effective_fields;
      const suggestion: VoiceSuggestion = {
        fields,
        uncertain: interpretation.draft.uncertain,
        notSelected: interpretation.draft.not_selected ?? [],
        unmatched: interpretation.draft.unmatched_mentions.map((mention) => mention.phrase),
      };
      const empty = kind === "onboarding_work" ? !fields.trade && !(fields.services_offered ?? []).length : !fields.city && !(fields.service_areas ?? []).length;
      if (!empty) onSuggest(suggestion);
      setResult({ heard: transcription.text, simulated: transcription.simulated || interpretation.simulated, suggestion, empty });
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  const stage = result ? 3 : busy ? 2 : 1;
  const stepState = (n: number) => (n < stage ? "done" : n === stage ? "current" : "pending");
  const join = (items: string[]) => items.join(language === "ur" ? "، " : ", ");

  return (
    <section aria-labelledby={`${kind}-voice-heading`} className="card space-y-3 border-primary/30 p-4">
      <h2 id={`${kind}-voice-heading`} className="flex items-center gap-2 font-bold text-primary">
        <span className="grid size-9 place-items-center rounded-full bg-primary-soft"><Mic className="size-5" aria-hidden /></span>
        {t("voiceAnswer.open")}
      </h2>
      <p className="text-sm">{t(kind === "onboarding_work" ? "voiceAnswer.intro.work" : "voiceAnswer.intro.areas")}</p>
      <ol className="space-y-1" aria-label={t("voiceAnswer.stepsLabel")}>
        <StepItem n={1} label={t("voiceAnswer.step.record")} state={stepState(1)} />
        <StepItem n={2} label={t("voiceAnswer.step.process")} state={stepState(2)} />
        <StepItem n={3} label={t("voiceAnswer.step.check")} state={stepState(3)} />
      </ol>
      <VoiceCapture audio={audio} onAudio={onAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={busy !== null} />
      <Button fullWidth disabled={!audio || busy !== null} loading={busy !== null} loadingLabel={busy ? t(`voiceAnswer.busy.${busy}`) : undefined}
        icon={<Sparkles className="size-5" aria-hidden />} onClick={() => void run()}>
        {t("voiceAnswer.fill")}
      </Button>
      {busy && (
        <p role="status" className="flex items-center gap-2 text-sm font-bold text-primary">
          <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden />
          {t(`voiceAnswer.busy.${busy}`)}
        </p>
      )}
      {failure !== null && (
        <Alert tone="warning" title={t("voiceAnswer.failed")}>
          <p>{describeError(failure, t)}</p>
          <p className="text-sm">{t("voiceAnswer.keptRecording")}</p>
          <Button variant="secondary" className="mt-2" icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => void run()}>
            {t("common.retry")}
          </Button>
        </Alert>
      )}
      {result && (
        <div className="space-y-2" role="status">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold">{t("voiceAnswer.heard")}</span>
            <SimulatedBadge show={result.simulated} />
          </div>
          <blockquote dir={textDir(result.heard)} className="rounded-xl border border-line bg-surface p-3">{result.heard}</blockquote>
          {result.empty ? <Alert tone="info">{t("voiceAnswer.nothingFound")}</Alert> : <Alert tone="success">{t("voiceAnswer.applied")}</Alert>}
          {result.suggestion.uncertain.length > 0 && <p className="text-sm font-bold">{t("voiceAnswer.unclear")}</p>}
          {result.suggestion.notSelected.length > 0 && (
            <p className="text-sm">{t("voiceAnswer.notGoing", { areas: join(result.suggestion.notSelected.map((code) => describe?.(code) ?? code)) })}</p>
          )}
          {result.suggestion.unmatched.length > 0 && <p className="text-sm text-muted">{t("voiceAnswer.unmatched", { phrases: join(result.suggestion.unmatched) })}</p>}
        </div>
      )}
    </section>
  );
}
