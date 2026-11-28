import { ArrowRight, CalendarClock, Keyboard, MapPin, Mic, RefreshCw, RotateCcw, Wallet, Wrench } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useNavigate } from "react-router";

import * as jobsApi from "../../api/jobs";
import * as voiceApi from "../../api/voice";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextArea } from "../../components/ui/TextArea";
import { clearDraft, readDraft, writeDraft } from "../../features/drafts";
import { textDir } from "../../features/jobs/text";
import { type CapturedAudio, VoiceCapture } from "../../features/voice/VoiceCapture";
import { StepHeader } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, LocalMessage } from "../../i18n/errors";

type Busy = "saving" | "transcribing" | "interpreting" | null;
type InputLanguage = "ur" | "en";
const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };
const DRAFT_KEY = "describe-job";

/** Everything typed, recorded or already created, kept in memory while the customer leaves this screen and returns. */
interface DescribeDraft {
  mode: "voice" | "text";
  hint: InputLanguage | null;
  typed: string;
  audio: CapturedAudio | null;
  jobId: string | null;
  clipId: string | null;
  transcriptionId: string | null;
}

/**
 * Step 1 — describe the job by recording, uploading audio or typing (Urdu or English).
 * A draft is saved FIRST, so the request survives a provider error or a reload; AI suggestions
 * are then attached. If speech-to-text or interpretation fails, the customer continues manually.
 * The input language follows the interface language until the customer picks one.
 */
export function DescribeJobPage() {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const navigate = useNavigate();
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const [saved] = useState(() => readDraft<DescribeDraft>(DRAFT_KEY));
  const [hint, setHint] = useState<InputLanguage | null>(saved?.hint ?? null);
  const [mode, setMode] = useState<"voice" | "text">(saved?.mode ?? "voice");
  const [audio, setAudio] = useState<CapturedAudio | null>(saved?.audio ?? null);
  const [typed, setTyped] = useState(saved?.typed ?? "");
  // Progress kept across retries (and visits elsewhere) so nothing is created twice.
  const [jobId, setJobId] = useState<string | null>(saved?.jobId ?? null);
  const [clipId, setClipId] = useState<string | null>(saved?.clipId ?? null);
  const [transcriptionId, setTranscriptionId] = useState<string | null>(saved?.transcriptionId ?? null);
  const [busy, setBusy] = useState<Busy>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const inputLanguage: InputLanguage = hint ?? language;
  const ready = mode === "text" ? typed.trim().length > 0 : audio !== null;
  const locked = jobId !== null;

  useEffect(() => {
    if (!typed && !audio && !jobId && !hint && mode === "voice") clearDraft(DRAFT_KEY);
    else writeDraft(DRAFT_KEY, { mode, hint, typed, audio, jobId, clipId, transcriptionId } satisfies DescribeDraft);
  }, [mode, hint, typed, audio, jobId, clipId, transcriptionId]);

  function done(id: string) {
    clearDraft(DRAFT_KEY);
    navigate(`/customer/requests/${id}/details`);
  }

  async function run() {
    setFailure(null);
    let id = jobId;
    try {
      if (mode === "text") {
        if (!id) {
          setBusy("saving");
          id = (await jobsApi.createTextJob(typed.trim(), inputLanguage)).id;
          setJobId(id);
        }
        setBusy("interpreting");
        const interpretation = await voiceApi.interpretText("job_description", typed.trim(), inputLanguage);
        await jobsApi.attachSource(id, { interpretation_id: interpretation.id });
      } else {
        let clip = clipId;
        if (!id || !clip) {
          if (!audio) return;
          setBusy("saving");
          clip = (await voiceApi.uploadClip(audio.blob, audio.filename, "job_description", audio.source)).id;
          setClipId(clip);
          id = (await jobsApi.createVoiceJob(clip, inputLanguage)).id;
          setJobId(id);
        }
        let transcription = transcriptionId;
        if (!transcription) {
          setBusy("transcribing");
          const result = await voiceApi.transcribe(clip, inputLanguage);
          await jobsApi.attachSource(id, { transcription_id: result.id });
          if (result.no_speech || !result.text.trim()) throw new LocalMessage("jobs.describe.noSpeech");
          transcription = result.id;
          setTranscriptionId(transcription);
        }
        setBusy("interpreting");
        const interpretation = await voiceApi.interpretTranscription("job_description", transcription, inputLanguage);
        await jobsApi.attachSource(id, { interpretation_id: interpretation.id });
      }
      done(id);
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

  // A draft was already created (an earlier attempt, maybe before a visit elsewhere): retry, go on, or start over.
  const stuck = failure !== null || (locked && busy === null);
  const choice = (value: "voice" | "text", title: string, icon: ReactNode) => (
    <button key={value} type="button" disabled={locked} aria-pressed={mode === value} onClick={() => setMode(value)}
      className={`inline-flex min-h-12 flex-1 items-center justify-center gap-2 rounded-lg px-4 font-bold transition-colors disabled:opacity-60 sm:flex-none sm:min-w-36 ${
        mode === value ? "bg-white text-primary shadow-sm ring-1 ring-primary/30" : "text-muted hover:text-primary"}`}>
      {icon}
      <span>{title}</span>
    </button>
  );

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,44rem)_minmax(14rem,20rem)] lg:gap-10">
      <div className="min-w-0 space-y-5">
        <StepHeader step={1} flow="request" title={t("jobs.describe.title")} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex w-full rounded-xl bg-[#eef1f7] p-1 sm:w-auto" role="group" aria-label={t("jobs.describe.howLabel")}>
            {choice("voice", t("jobs.describe.speak"), <Mic className="size-5" aria-hidden />)}
            {choice("text", t("jobs.describe.type"), <Keyboard className="size-5" aria-hidden />)}
          </div>
          <div className="flex items-center gap-2 text-sm" role="group" aria-label={t("jobs.describe.languageLabel")}>
            <span className="text-muted">{t("jobs.describe.languageShort")}</span>
            {(["ur", "en"] as const).map((code) => (
              <button key={code} type="button" lang={code} disabled={locked} aria-pressed={inputLanguage === code} onClick={() => setHint(code)}
                className={`min-h-11 rounded-lg border px-3 font-bold disabled:opacity-60 ${
                  inputLanguage === code ? "border-primary bg-primary-soft text-primary" : "border-line bg-white text-muted hover:border-primary/50"}`}>
                {code === "ur" ? "اردو" : "English"}
              </button>
            ))}
          </div>
        </div>

        {mode === "voice" ? (
          <div className="space-y-2">
            <VoiceCapture audio={audio} onAudio={setAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={locked || busy !== null} />
            <p className="text-sm text-muted">{t("jobs.describe.voiceNote")}</p>
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
            dir={typed ? textDir(typed) : inputLanguage === "ur" ? "rtl" : "ltr"}
          />
        )}

        {busy && (
          <p role="status" className="font-bold">
            {t(`jobs.describe.busy.${busy}`)}
          </p>
        )}

        {failure !== null ? (
          <Alert tone="warning" title={t("jobs.describe.failedTitle")}>
            <p>{describeError(failure, t)}</p>
            <p>{jobId ? t("jobs.describe.draftKept") : t("jobs.describe.nothingSaved")}</p>
          </Alert>
        ) : stuck ? (
          <Alert tone="info">{t("jobs.describe.draftKept")}</Alert>
        ) : null}

        {stuck ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Button icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => void run()} disabled={busy !== null}>
              {t("common.retry")}
            </Button>
            {jobId && (
              <Button variant="secondary" icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />} onClick={() => done(jobId)}>
                {t("jobs.describe.continueManually")}
              </Button>
            )}
            <Button variant="ghost" icon={<RotateCcw className="size-5" aria-hidden />} onClick={startOver}>
              {t("jobs.describe.startOver")}
            </Button>
          </div>
        ) : (
          <Button className="w-full sm:w-auto sm:min-w-56" disabled={!ready} loading={busy !== null} loadingLabel={busy ? t(`jobs.describe.busy.${busy}`) : undefined}
            icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />} onClick={() => void run()}>
            {t("jobs.describe.continue")}
          </Button>
        )}
      </div>

      <aside aria-labelledby="describe-tips" className="hidden space-y-3 rounded-2xl border border-line bg-white p-4 lg:block">
        <h2 id="describe-tips" className="font-bold">{t("jobs.describe.tipsTitle")}</h2>
        <ul className="space-y-2 text-sm">
          {([
            [<Wrench key="w" className="size-4" aria-hidden />, t("jobs.describe.tip.work")],
            [<MapPin key="m" className="size-4" aria-hidden />, t("jobs.describe.tip.area")],
            [<CalendarClock key="c" className="size-4" aria-hidden />, t("jobs.describe.tip.time")],
            [<Wallet key="b" className="size-4" aria-hidden />, t("jobs.describe.tip.budget")],
          ] as const).map(([icon, text]) => (
            <li key={text} className="flex items-center gap-2"><span className="text-primary">{icon}</span>{text}</li>
          ))}
        </ul>
        <p className="text-xs text-muted">{t("jobs.describe.tipPrivacy")}</p>
      </aside>
    </div>
  );
}
