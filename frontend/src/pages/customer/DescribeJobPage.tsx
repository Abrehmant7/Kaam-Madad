import { ArrowRight, Keyboard, Languages, Mic, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import * as jobsApi from "../../api/jobs";
import * as voiceApi from "../../api/voice";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { TextArea } from "../../components/ui/TextArea";
import { textDir } from "../../features/jobs/text";
import { type CapturedAudio, VoiceCapture } from "../../features/voice/VoiceCapture";
import { StepHeader } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, LocalMessage } from "../../i18n/errors";

type Busy = "saving" | "transcribing" | "interpreting" | null;
const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };

/**
 * Step 1 — describe the job by recording, uploading audio or typing (Urdu or English).
 * A draft is saved FIRST, so the request survives a provider error or a reload; AI suggestions
 * are then attached. If speech-to-text or interpretation fails, the customer continues manually.
 */
export function DescribeJobPage() {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const navigate = useNavigate();
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const [hint, setHint] = useState<("ur" | "en")[]>([language]);
  const [mode, setMode] = useState<"voice" | "text">("voice");
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [typed, setTyped] = useState("");
  // Progress kept across retries so nothing is created twice.
  const [jobId, setJobId] = useState<string | null>(null);
  const [clipId, setClipId] = useState<string | null>(null);
  const [transcriptionId, setTranscriptionId] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const language_ = hint[0] ?? language;
  const ready = mode === "text" ? typed.trim().length > 0 : audio !== null;
  const locked = jobId !== null;

  async function run() {
    setFailure(null);
    let id = jobId;
    try {
      if (mode === "text") {
        if (!id) {
          setBusy("saving");
          id = (await jobsApi.createTextJob(typed.trim(), language_)).id;
          setJobId(id);
        }
        setBusy("interpreting");
        const interpretation = await voiceApi.interpretText("job_description", typed.trim(), language_);
        await jobsApi.attachSource(id, { interpretation_id: interpretation.id });
      } else {
        let clip = clipId;
        if (!id || !clip) {
          if (!audio) return;
          setBusy("saving");
          clip = (await voiceApi.uploadClip(audio.blob, audio.filename, "job_description", audio.source)).id;
          setClipId(clip);
          id = (await jobsApi.createVoiceJob(clip, language_)).id;
          setJobId(id);
        }
        let transcription = transcriptionId;
        if (!transcription) {
          setBusy("transcribing");
          const result = await voiceApi.transcribe(clip, language_);
          await jobsApi.attachSource(id, { transcription_id: result.id });
          if (result.no_speech || !result.text.trim()) throw new LocalMessage("jobs.describe.noSpeech");
          transcription = result.id;
          setTranscriptionId(transcription);
        }
        setBusy("interpreting");
        const interpretation = await voiceApi.interpretTranscription("job_description", transcription, language_);
        await jobsApi.attachSource(id, { interpretation_id: interpretation.id });
      }
      navigate(`/customer/requests/${id}/details`);
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  function startOver() {
    setJobId(null);
    setClipId(null);
    setTranscriptionId(null);
    setAudio(null);
    setTyped("");
    setFailure(null);
  }

  const languageOptions = (["ur", "en"] as const).map((code) => ({
    value: code,
    label: code === "ur" ? "اردو" : "English",
    lang: code,
    icon: <Languages className="size-7" aria-hidden />,
  }));

  return (
    <div className="space-y-5">
      <StepHeader step={1} title={t("jobs.describe.title")} />
      <p>{t("jobs.describe.intro")}</p>

      <IconTileGroup label={t("jobs.describe.languageLabel")} mode="single" options={languageOptions} value={hint} onChange={(next) => !locked && setHint(next)} />

      <div className="grid grid-cols-2 gap-2">
        <Button variant={mode === "voice" ? "primary" : "secondary"} disabled={locked} icon={<Mic className="size-5" aria-hidden />} aria-pressed={mode === "voice"} onClick={() => setMode("voice")}>
          {t("jobs.describe.speak")}
        </Button>
        <Button variant={mode === "text" ? "primary" : "secondary"} disabled={locked} icon={<Keyboard className="size-5" aria-hidden />} aria-pressed={mode === "text"} onClick={() => setMode("text")}>
          {t("jobs.describe.type")}
        </Button>
      </div>

      {mode === "voice" ? (
        <div className="space-y-2">
          <p className="text-sm text-muted">{t("jobs.describe.voiceNote")}</p>
          <VoiceCapture audio={audio} onAudio={setAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={locked || busy !== null} />
        </div>
      ) : (
        <TextArea
          label={t("jobs.describe.textLabel")}
          hint={t("jobs.describe.textHint")}
          value={typed}
          onChange={setTyped}
          disabled={locked || busy !== null}
          maxLength={2000}
          rows={5}
          dir={typed ? textDir(typed) : language === "ur" ? "rtl" : "ltr"}
        />
      )}

      {busy && (
        <p role="status" className="font-bold">
          {t(`jobs.describe.busy.${busy}`)}
        </p>
      )}

      {failure !== null && (
        <Alert tone="warning" title={t("jobs.describe.failedTitle")}>
          <p>{describeError(failure, t)}</p>
          <p>{jobId ? t("jobs.describe.draftKept") : t("jobs.describe.nothingSaved")}</p>
        </Alert>
      )}

      {failure !== null ? (
        <div className="grid gap-2">
          <Button icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => void run()} disabled={busy !== null}>
            {t("common.retry")}
          </Button>
          {jobId && (
            <Button variant="secondary" icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />} onClick={() => navigate(`/customer/requests/${jobId}/details`)}>
              {t("jobs.describe.continueManually")}
            </Button>
          )}
          <Button variant="ghost" icon={<RotateCcw className="size-5" aria-hidden />} onClick={startOver}>
            {t("jobs.describe.startOver")}
          </Button>
        </div>
      ) : (
        <Button fullWidth disabled={!ready} loading={busy !== null} loadingLabel={busy ? t(`jobs.describe.busy.${busy}`) : undefined}
          icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />} onClick={() => void run()}>
          {t("jobs.describe.continue")}
        </Button>
      )}
    </div>
  );
}
