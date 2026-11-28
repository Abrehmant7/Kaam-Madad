import { RefreshCw, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import * as voiceApi from "../../api/voice";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { SimulatedBadge } from "./SimulatedBadge";

/**
 * Reads confirmed text aloud (UX-03, MSG-02). The text is always shown, so a
 * synthesis failure never hides information; failures offer a retry. Audio is
 * fetched privately and played from a blob URL.
 */
export function ReadAloud({ text, language, showText = true }: {
  text: string;
  language: "ur" | "en";
  /** False only where the same details are already shown next to the button (e.g. the invitation card). */
  showText?: boolean;
}) {
  const { t } = useI18n();
  const [state, setState] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const [failure, setFailure] = useState<unknown>(null);
  const [simulated, setSimulated] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const url = useRef<string | null>(null);

  useEffect(
    () => () => {
      audio.current?.pause();
      if (url.current) URL.revokeObjectURL(url.current);
    },
    [],
  );

  async function play() {
    if (state === "playing") {
      audio.current?.pause();
      setState("idle");
      return;
    }
    setState("loading");
    setFailure(null);
    try {
      const synthesis = await voiceApi.synthesise(text, language);
      setSimulated(synthesis.simulated);
      const blob = await voiceApi.fetchPrivateAudio(synthesis.content_url);
      if (url.current) URL.revokeObjectURL(url.current);
      url.current = URL.createObjectURL(blob);
      const player = new Audio(url.current);
      audio.current = player;
      player.onended = () => setState("idle");
      await player.play();
      setState("playing");
    } catch (caught) {
      setFailure(caught);
      setState("error");
    }
  }

  return (
    <div className="space-y-3">
      {showText && (
        <blockquote dir="auto" lang={language} className="rounded-xl border border-line bg-white p-3">
          {text}
        </blockquote>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="soft"
          loading={state === "loading"}
          loadingLabel={t("audio.loading")}
          icon={state === "error" ? <RefreshCw className="size-5" aria-hidden /> : <Volume2 className="size-5" aria-hidden />}
          onClick={() => void play()}
        >
          {state === "playing" ? t("audio.stop") : state === "error" ? t("common.retry") : t("voice.readAloud")}
        </Button>
        <SimulatedBadge show={simulated} />
      </div>
      {simulated && <p className="text-sm text-muted">{t("voice.simulatedSpeech")}</p>}
      {failure !== null && (
        <Alert tone="danger" title={t("voice.readAloudFailed")}>
          {describeError(failure, t)}
        </Alert>
      )}
    </div>
  );
}
