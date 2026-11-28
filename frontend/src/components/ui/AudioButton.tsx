import { CircleAlert, LoaderCircle, Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useI18n } from "../../i18n/context";

interface AudioButtonProps {
  /** What will be played, e.g. "Instructions" — used in the accessible label. */
  label: string;
  /** URL of recorded audio (e.g. a prerecorded instruction file). */
  src?: string;
  /** Or a handler that produces/plays audio (e.g. a TTS adapter in M3). */
  onPlay?: () => Promise<void> | void;
  /** Or a loader that returns a playable URL on first play (e.g. server-synthesised instructions). */
  resolveSrc?: () => Promise<string>;
}

type PlayState = "idle" | "loading" | "playing" | "error";

/**
 * Play / replay control for spoken instructions (UX-03).
 *
 * Renders NOTHING when no audio source or handler exists, so the UI never
 * promises speech it cannot produce. Failures show a readable fallback message
 * and the button stays available for a retry.
 */
export function AudioButton({ label, src, onPlay, resolveSrc }: AudioButtonProps) {
  const { t } = useI18n();
  const [state, setState] = useState<PlayState>("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => () => audioRef.current?.pause(), []);

  if (!src && !onPlay && !resolveSrc) return null;

  async function play() {
    if (state === "playing" && audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setState("idle");
      return;
    }
    setState("loading");
    try {
      if (onPlay) {
        await onPlay();
        setState("idle");
        return;
      }
      const audio = audioRef.current ?? new Audio(src ?? (resolveSrc ? await resolveSrc() : undefined));
      audioRef.current = audio;
      audio.onended = () => setState("idle");
      audio.onerror = () => setState("error");
      await audio.play();
      setState("playing");
    } catch {
      setState("error");
    }
  }

  const playing = state === "playing";
  return (
    <div className="inline-flex flex-col gap-1">
      <button
        type="button"
        onClick={() => void play()}
        aria-label={`${playing ? t("audio.stop") : t("audio.play")}: ${label}`}
        aria-busy={state === "loading" || undefined}
        className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary-soft px-4 font-bold text-primary hover:bg-[#dce6ff]"
      >
        {state === "loading" ? (
          <LoaderCircle className="size-5 motion-safe:animate-spin" aria-hidden />
        ) : playing ? (
          <Square className="size-5" aria-hidden />
        ) : (
          <Volume2 className="size-5" aria-hidden />
        )}
        <span>{playing ? t("audio.stop") : state === "loading" ? t("audio.loading") : t("audio.play")}</span>
      </button>
      {state === "error" && (
        <p role="alert" className="flex items-center gap-1.5 text-sm font-bold text-danger-strong">
          <CircleAlert className="size-4" aria-hidden />
          {t("audio.failed")}
        </p>
      )}
    </div>
  );
}
