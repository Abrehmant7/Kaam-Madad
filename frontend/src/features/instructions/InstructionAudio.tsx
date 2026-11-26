import { Info } from "lucide-react";
import { useEffect, useRef } from "react";

import { apiRequest } from "../../api/client";
import { useAuth } from "../../auth/context";
import { AudioButton } from "../../components/ui/AudioButton";
import { useI18n } from "../../i18n/context";

export type InstructionKey = "signup_password" | "onboarding_work" | "onboarding_areas" | "identity_consent";

/**
 * A FIXED instruction: always shown as text, with a play button when the server can speak (UX-03).
 * Only the instruction key is sent; the server owns the text, so nothing the user typed
 * (passwords, codes, CNIC numbers) can reach the speech provider.
 */
export function InstructionAudio({ id }: { id: InstructionKey }) {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const url = useRef<string | null>(null);
  const tts = config?.ai?.text_to_speech;

  useEffect(
    () => () => {
      if (url.current) URL.revokeObjectURL(url.current);
    },
    [],
  );

  async function resolveSrc() {
    const blob = await apiRequest<Blob>(`/instructions/${id}/audio/?language=${language}`, { responseType: "blob", timeoutMs: 60000 });
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = URL.createObjectURL(blob);
    return url.current;
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-3">
      <p className="flex items-start gap-2">
        <Info className="mt-1 size-5 shrink-0 text-primary" aria-hidden />
        <span>{t(`instructions.${id}`)}</span>
      </p>
      {tts?.available && (
        <div className="flex flex-col gap-1">
          {/* Remount per language so the cached audio matches the text shown. */}
          <AudioButton key={language} label={t("instructions.listen")} resolveSrc={resolveSrc} />
          {tts.simulated && <p className="text-xs text-muted">{t("voice.simulatedSpeech")}</p>}
        </div>
      )}
    </div>
  );
}
