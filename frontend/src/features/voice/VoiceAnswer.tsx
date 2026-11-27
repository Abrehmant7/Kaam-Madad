import { ChevronDown, Mic, Sparkles } from "lucide-react";
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

/**
 * Optional "Answer by voice" for a worker signup screen. The recording is transcribed in the spoken language and
 * the text AI suggests catalog choices for THIS screen only. Suggestions are handed to the page, which shows them in
 * its normal editable choices; nothing is saved until the worker presses the screen's own Save button. Any failure
 * leaves manual selection untouched.
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

  return (
    <details className="group rounded-2xl border border-primary/40 bg-white p-3">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 font-bold text-primary">
        <span className="flex items-center gap-2">
          <Mic className="size-5" aria-hidden />
          {t("voiceAnswer.open")}
        </span>
        <ChevronDown className="size-5 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-sm">{t(kind === "onboarding_work" ? "voiceAnswer.intro.work" : "voiceAnswer.intro.areas")}</p>
        <VoiceCapture audio={audio} onAudio={onAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={busy !== null} />
        <Button fullWidth disabled={!audio || busy !== null} loading={busy !== null} loadingLabel={busy ? t(`voiceAnswer.busy.${busy}`) : undefined}
          icon={<Sparkles className="size-5" aria-hidden />} onClick={() => void run()}>
          {t("voiceAnswer.fill")}
        </Button>
        {failure !== null && (
          <Alert tone="warning" title={t("voiceAnswer.failed")}>
            {describeError(failure, t)}
          </Alert>
        )}
        {result && (
          <div className="space-y-2" role="status">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold">{t("voiceAnswer.heard")}</span>
              <SimulatedBadge show={result.simulated} />
            </div>
            <blockquote dir={textDir(result.heard)} className="rounded-xl border border-line bg-surface p-3">{result.heard}</blockquote>
            {result.empty ? (
              <Alert tone="info">{t("voiceAnswer.nothingFound")}</Alert>
            ) : (
              <Alert tone="success">{t("voiceAnswer.applied")}</Alert>
            )}
            {result.suggestion.uncertain.length > 0 && <p className="text-sm font-bold">{t("voiceAnswer.unclear")}</p>}
            {result.suggestion.notSelected.length > 0 && (
              <p className="text-sm">
                {t("voiceAnswer.notGoing", { areas: result.suggestion.notSelected.map((code) => describe?.(code) ?? code).join(language === "ur" ? "، " : ", ") })}
              </p>
            )}
            {result.suggestion.unmatched.length > 0 && (
              <p className="text-sm text-muted">{t("voiceAnswer.unmatched", { phrases: result.suggestion.unmatched.join(language === "ur" ? "، " : ", ") })}</p>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
