import { Mic, MessageSquareText, Play, Send, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import * as convApi from "../../api/conversations";
import * as voiceApi from "../../api/voice";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { textDir } from "../jobs/text";
import { formatTime } from "../jobs/time";
import { type CapturedAudio, VoiceCapture } from "../voice/VoiceCapture";

const POLL_MS = 5000;
const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };

function VoicePlayer({ url }: { url: string }) {
  const { t } = useI18n();
  const [state, setState] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const audio = useRef<HTMLAudioElement | null>(null);
  const objectUrl = useRef<string | null>(null);
  useEffect(() => () => {
    audio.current?.pause();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
  }, []);
  async function toggle() {
    if (state === "playing") {
      audio.current?.pause();
      setState("idle");
      return;
    }
    setState("loading");
    try {
      if (!audio.current) {
        objectUrl.current = URL.createObjectURL(await convApi.fetchMessageAudio(url));
        audio.current = new Audio(objectUrl.current);
        audio.current.onended = () => setState("idle");
      }
      await audio.current.play();
      setState("playing");
    } catch {
      setState("error");
    }
  }
  return (
    <div className="flex flex-col gap-1">
      <Button variant="secondary" className="min-h-11 self-start" loading={state === "loading"} loadingLabel={t("audio.loading")}
        icon={state === "playing" ? <Square className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />} onClick={() => void toggle()}>
        {state === "playing" ? t("audio.stop") : t("conv.playVoice")}
      </Button>
      {state === "error" && <p className="text-sm text-danger-strong">{t("audio.failed")}</p>}
    </div>
  );
}

function Bubble({ message }: { message: convApi.Message }) {
  const { t, language } = useI18n();
  return (
    <li className={`flex ${message.mine ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] space-y-2 rounded-2xl border p-3 ${message.mine ? "border-primary/30 bg-primary/10" : "border-line bg-white"}`}>
        <p className="text-xs font-bold text-muted">
          {message.mine ? t("conv.you") : t(`conv.role.${message.sender_role}`)} · <bdi dir="ltr">{formatTime(message.created_at, language)}</bdi>
        </p>
        {message.kind === "voice" && message.audio_url && <VoicePlayer url={message.audio_url} />}
        {message.text ? (
          <p dir={textDir(message.text)} className="whitespace-pre-line">{message.text}</p>
        ) : (
          message.kind === "voice" && <StatusBadge tone="warning">{t("conv.captionUnavailable")}</StatusBadge>
        )}
        {message.caption_status === "typed" && <p className="text-xs text-muted">{t("conv.captionTyped")}</p>}
        {message.caption_status === "approved" && <p className="text-xs text-muted">{t("conv.captionApproved")}</p>}
      </div>
    </li>
  );
}

/** Messages (paginated, polled) and the composer. Polling only appends; the draft being typed is untouched. */
export function MessageThread({ invitationId, canWrite, onActivity, onClosed }: {
  invitationId: string; canWrite: boolean; onActivity?: () => void; onClosed?: () => void;
}) {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const [messages, setMessages] = useState<convApi.Message[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadFailure, setLoadFailure] = useState<unknown>(null);
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [text, setText] = useState("");
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [caption, setCaption] = useState("");
  const [voice, setVoice] = useState<{ clipId: string; transcriptionId: string | null; proposal: string | null; failed: boolean } | null>(null);
  const [busy, setBusy] = useState<"caption" | "send" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const pendingId = useRef<string | null>(null); // reused for retries of the same send
  const lastId = useRef<string | null>(null);

  const merge = useCallback((incoming: convApi.Message[], position: "end" | "start") => {
    setMessages((current) => {
      const known = new Set(current.map((m) => m.id));
      const fresh = incoming.filter((m) => !known.has(m.id));
      const next = position === "end" ? [...current, ...fresh] : [...fresh, ...current];
      lastId.current = next.at(-1)?.id ?? null;
      return next;
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    convApi.fetchMessages(invitationId, {}, controller.signal)
      .then((page) => { merge(page.results, "end"); setHasMore(Boolean(page.has_more_before)); })
      .catch((error: unknown) => !controller.signal.aborted && setLoadFailure(error));
    const timer = window.setInterval(() => {
      const after = lastId.current;
      convApi.fetchMessages(invitationId, after ? { after } : {})
        .then((page) => { if (page.results.length) { merge(page.results, "end"); onActivity?.(); } })
        .catch(() => undefined); // polling failures are silent; the next poll retries
    }, POLL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [invitationId, merge, onActivity]);

  // Stable: VoiceCapture hands over a finished recording from an effect that depends on this callback.
  const takeAudio = useCallback((next: CapturedAudio | null) => {
    setAudio(next);
    setVoice(null);
    setCaption("");
    pendingId.current = null;
  }, []);

  async function loadEarlier() {
    const first = messages[0];
    if (!first) return;
    const page = await convApi.fetchMessages(invitationId, { before: first.id });
    merge(page.results, "start");
    setHasMore(Boolean(page.has_more_before));
  }

  async function prepareCaption() {
    if (!audio) return;
    setFailure(null);
    setBusy("caption");
    let clipId = voice?.clipId ?? null;
    try {
      if (!clipId) clipId = (await voiceApi.uploadClip(audio.blob, audio.filename, "message", audio.source)).id;
      try {
        const transcription = await voiceApi.transcribe(clipId, language);
        const proposal = transcription.no_speech ? "" : transcription.text;
        setVoice({ clipId, transcriptionId: transcription.id, proposal, failed: false });
        setCaption(proposal);
      } catch (error) {
        setVoice({ clipId, transcriptionId: null, proposal: null, failed: true });
        setFailure(error);
      }
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  async function send() {
    setFailure(null);
    setBusy("send");
    pendingId.current = pendingId.current ?? convApi.newClientId();
    try {
      const payload: convApi.SendPayload =
        mode === "text"
          ? { client_id: pendingId.current, kind: "text", text: text.trim() }
          : { client_id: pendingId.current, kind: "voice", audio_clip_id: voice!.clipId, text: caption.trim(), ...(voice!.transcriptionId ? { transcription_id: voice!.transcriptionId } : {}) };
      const message = await convApi.sendMessage(invitationId, payload);
      merge([message], "end");
      pendingId.current = null;
      setText("");
      setAudio(null);
      setVoice(null);
      setCaption("");
      onActivity?.();
    } catch (error) {
      setFailure(error); // the same send ID is kept, so pressing Send again cannot duplicate
      if (error instanceof ApiError && error.code === "conversation_closed") onClosed?.();
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="messages-heading" className="space-y-3">
      <h2 id="messages-heading" className="flex items-center gap-2 text-lg font-bold">
        <MessageSquareText className="size-5" aria-hidden />
        {t("conv.messages")}
      </h2>
      {loadFailure !== null && <Alert tone="danger">{describeError(loadFailure, t)}</Alert>}
      {hasMore && (
        <Button variant="ghost" onClick={() => void loadEarlier()}>
          {t("conv.loadEarlier")}
        </Button>
      )}
      {messages.length === 0 ? (
        <p className="text-muted">{t("conv.empty")}</p>
      ) : (
        <ul className="space-y-2" aria-live="polite">
          {messages.map((message) => (
            <Bubble key={message.id} message={message} />
          ))}
        </ul>
      )}

      {canWrite ? (
        <div className="space-y-3 rounded-2xl border border-line bg-white p-3">
          <div className="grid grid-cols-2 gap-2">
            <Button variant={mode === "text" ? "primary" : "secondary"} aria-pressed={mode === "text"} icon={<MessageSquareText className="size-5" aria-hidden />} onClick={() => setMode("text")}>
              {t("conv.text")}
            </Button>
            <Button variant={mode === "voice" ? "primary" : "secondary"} aria-pressed={mode === "voice"} icon={<Mic className="size-5" aria-hidden />} onClick={() => setMode("voice")}>
              {t("conv.voice")}
            </Button>
          </div>
          {mode === "text" ? (
            <TextArea label={t("conv.messageLabel")} hint={t("conv.privacyHint")} value={text} onChange={(value) => { setText(value); pendingId.current = null; }}
              maxLength={1000} rows={3} dir={text ? textDir(text) : language === "ur" ? "rtl" : "ltr"} />
          ) : (
            <div className="space-y-3">
              <VoiceCapture audio={audio} onAudio={takeAudio}
                maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={busy !== null} />
              {audio && !voice && (
                <Button variant="secondary" loading={busy === "caption"} loadingLabel={t("conv.preparingCaption")} onClick={() => void prepareCaption()}>
                  {t("conv.prepareCaption")}
                </Button>
              )}
              {voice && (
                <>
                  {voice.failed ? (
                    <Alert tone="warning">{t("conv.captionFailed")}</Alert>
                  ) : (
                    <p className="text-sm text-muted">{t("conv.captionCheck")}</p>
                  )}
                  <TextArea label={t("conv.captionLabel")} value={caption} onChange={setCaption} maxLength={1000} rows={3}
                    dir={caption ? textDir(caption) : language === "ur" ? "rtl" : "ltr"} />
                  {!caption.trim() && <StatusBadge tone="warning">{t("conv.captionUnavailable")}</StatusBadge>}
                </>
              )}
            </div>
          )}
          {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
          <Button fullWidth loading={busy === "send"} loadingLabel={t("conv.sending")} icon={<Send className="size-5" aria-hidden />}
            disabled={busy !== null || (mode === "text" ? !text.trim() : !voice)} onClick={() => void send()}>
            {mode === "voice" && voice && !caption.trim() ? t("conv.sendWithoutCaption") : t("conv.send")}
          </Button>
        </div>
      ) : (
        <Alert tone="info">{t("conv.closed")}</Alert>
      )}
    </section>
  );
}
