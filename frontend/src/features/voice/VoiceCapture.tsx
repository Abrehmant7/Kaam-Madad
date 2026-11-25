import { Mic, RotateCcw, Square, Upload } from "lucide-react";
import { type ChangeEvent, useEffect, useId, useRef, useState } from "react";

import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { formatMinutesSeconds } from "../../hooks/useCountdown";
import { useI18n } from "../../i18n/context";
import { useRecorder } from "./useRecorder";

export interface CapturedAudio {
  blob: Blob;
  filename: string;
  source: "recording" | "upload";
  seconds: number | null;
}

const ACCEPT = "audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,audio/aac,audio/ogg,audio/opus,audio/flac,.wav,.mp3,.m4a,.aac,.ogg,.opus,.flac";

function readDuration(blob: Blob): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio();
    const done = (value: number | null) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    audio.preload = "metadata";
    audio.onloadedmetadata = () => done(Number.isFinite(audio.duration) ? audio.duration : null);
    audio.onerror = () => done(null);
    audio.src = url;
    window.setTimeout(() => done(null), 3000);
  });
}

interface VoiceCaptureProps {
  audio: CapturedAudio | null;
  onAudio: (audio: CapturedAudio | null) => void;
  maxSeconds: number;
  maxBytes: number;
  disabled?: boolean;
}

/**
 * Record (push-to-talk, ≤ maxSeconds) or upload a voice clip, then replay it.
 * Microphone permission is requested only when the user presses Record. If
 * recording is unsupported or denied, upload (and typing, offered by the page)
 * remain available. Checks here are a convenience — the server validates again.
 */
export function VoiceCapture({ audio, onAudio, maxSeconds, maxBytes, disabled = false }: VoiceCaptureProps) {
  const { t } = useI18n();
  const recorder = useRecorder(maxSeconds);
  const fileInput = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);

  // Hand a finished recording to the page.
  useEffect(() => {
    if (recorder.recording) {
      onAudio({ blob: recorder.recording.blob, filename: "recording.wav", source: "recording", seconds: recorder.recording.seconds });
    }
  }, [recorder.recording, onAudio]);

  // Object URL for replay, released when the audio changes.
  useEffect(() => {
    if (!audio) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(audio.blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [audio]);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    setUploadError(null);
    if (!file) return;
    if (file.size > maxBytes) {
      setUploadError(t("voice.fileTooLarge"));
      return;
    }
    const seconds = await readDuration(file);
    if (seconds !== null && seconds > maxSeconds + 0.25) {
      setUploadError(t("voice.fileTooLong"));
      return;
    }
    onAudio({ blob: file, filename: file.name || "upload", source: "upload", seconds });
  }

  const recording = recorder.state === "recording";
  const progress = Math.min(100, (recorder.elapsed / maxSeconds) * 100);

  return (
    <div className="space-y-3">
      {recorder.state === "unsupported" && <Alert tone="info">{t("voice.recordingUnsupported")}</Alert>}
      {recorder.state === "denied" && <Alert tone="warning">{t("voice.microphoneDenied")}</Alert>}
      {recorder.state === "error" && <Alert tone="warning">{t("voice.recordingFailed")}</Alert>}
      {uploadError && <Alert tone="danger">{uploadError}</Alert>}

      {recording ? (
        <div className="space-y-2 rounded-xl border-2 border-danger/40 bg-danger-soft p-3" role="status" aria-live="polite">
          <p className="flex items-center gap-2 font-bold text-danger-strong">
            <span className="size-3 rounded-full bg-danger motion-safe:animate-pulse" aria-hidden />
            {t("voice.recordingNow")}
            <Ltr>
              {formatMinutesSeconds(Math.floor(recorder.elapsed))} / {formatMinutesSeconds(maxSeconds)}
            </Ltr>
          </p>
          <div className="h-2 overflow-hidden rounded-full bg-white" aria-hidden>
            <div className="h-full bg-danger" style={{ width: `${progress}%` }} />
          </div>
          <Button variant="danger" fullWidth icon={<Square className="size-5" aria-hidden />} onClick={recorder.stop}>
            {t("voice.stop")}
          </Button>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {recorder.state !== "unsupported" && (
            <Button
              fullWidth
              disabled={disabled}
              loading={recorder.state === "requesting"}
              loadingLabel={t("voice.askingMicrophone")}
              icon={audio ? <RotateCcw className="size-5" aria-hidden /> : <Mic className="size-5" aria-hidden />}
              onClick={() => {
                setUploadError(null);
                void recorder.start();
              }}
            >
              {audio ? t("voice.recordAgain") : t("voice.record", { seconds: maxSeconds })}
            </Button>
          )}
          <Button
            variant="secondary"
            fullWidth
            disabled={disabled}
            icon={<Upload className="size-5" aria-hidden />}
            onClick={() => fileInput.current?.click()}
          >
            {t("voice.upload")}
          </Button>
          <input
            ref={fileInput}
            id={inputId}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(event) => void handleFile(event)}
          />
        </div>
      )}
      <p className="text-sm text-muted">{t("voice.limits", { seconds: maxSeconds, megabytes: Math.round(maxBytes / 1024 / 1024) })}</p>

      {audio && url && !recording && (
        <div className="space-y-1 rounded-xl border border-line bg-white p-3">
          <p className="text-sm font-bold">
            {audio.source === "recording" ? t("voice.yourRecording") : t("voice.yourFile")}
            {audio.seconds !== null && (
              <>
                {" "}
                <Ltr className="font-normal text-muted">({audio.seconds.toFixed(1)} s)</Ltr>
              </>
            )}
          </p>
          {/* Replay of the user's own audio (local blob, never uploaded until they continue). */}
          <audio controls src={url} className="w-full" aria-label={t("voice.replay")} />
        </div>
      )}
    </div>
  );
}
