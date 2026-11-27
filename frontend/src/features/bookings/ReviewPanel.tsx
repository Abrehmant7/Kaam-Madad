import { Mic, Send, Star } from "lucide-react";
import { useCallback, useState } from "react";

import * as bookingsApi from "../../api/bookings";
import * as voiceApi from "../../api/voice";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { textDir } from "../jobs/text";
import { type CapturedAudio, VoiceCapture } from "../voice/VoiceCapture";

const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };
const STARS = ["1", "2", "3", "4", "5"] as const;

export function Stars({ rating }: { rating: number }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex items-center gap-0.5" role="img" aria-label={t("review.starsLabel", { rating })}>
      {STARS.map((value) => (
        <Star key={value} className={`size-5 ${Number(value) <= rating ? "fill-accent text-accent" : "text-muted"}`} aria-hidden />
      ))}
    </span>
  );
}

/** 1–5 stars as a radio group: 48 px targets, each star labelled for screen readers. */
function StarPicker({ value, onChange }: { value: number; onChange: (rating: number) => void }) {
  const { t } = useI18n();
  return (
    <fieldset className="space-y-2">
      <legend className="font-bold">{t("review.ratingLabel")}</legend>
      <div role="radiogroup" aria-label={t("review.ratingLabel")} className="flex gap-1" dir="ltr">
        {STARS.map((star) => {
          const n = Number(star);
          return (
            <button key={star} type="button" role="radio" aria-checked={value === n} aria-label={t("review.starsLabel", { rating: n })}
              className="flex size-12 items-center justify-center rounded-xl border border-line bg-white focus-visible:outline-2"
              onClick={() => onChange(n)}>
              <Star className={`size-7 ${n <= value ? "fill-accent text-accent" : "text-muted"}`} aria-hidden />
            </button>
          );
        })}
      </div>
      {value > 0 && <p className="text-sm">{t(`review.ratingWord.${value}` as never)}</p>}
    </fieldset>
  );
}

/** The job's review: shown to its author (and to the worker unless hidden); the form for an eligible customer. */
export function ReviewPanel({ booking, onDone }: { booking: bookingsApi.Booking; onDone: (review: bookingsApi.Review) => void }) {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const [rating, setRating] = useState(0);
  const [text, setText] = useState("");
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [voice, setVoice] = useState<{ clipId: string; transcriptionId: string | null } | null>(null);
  const [busy, setBusy] = useState<"draft" | "send" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [draftFailed, setDraftFailed] = useState(false);
  const takeAudio = useCallback((next: CapturedAudio | null) => { setAudio(next); setVoice(null); setDraftFailed(false); }, []);

  if (booking.review) {
    return (
      <section aria-labelledby="review-heading" className="space-y-2 rounded-2xl border border-line bg-white p-4">
        <h2 id="review-heading" className="text-lg font-bold">{booking.role === "customer" ? t("review.yours") : t("review.forYou")}</h2>
        <Stars rating={booking.review.rating} />
        {booking.review.text && <p dir={textDir(booking.review.text)} className="whitespace-pre-line">“{booking.review.text}”</p>}
        {booking.review.hidden && <StatusBadge tone="warning">{t("review.hidden")}</StatusBadge>}
      </section>
    );
  }
  if (!booking.actions.review) return null;

  async function draftFromVoice() {
    if (!audio) return;
    setFailure(null);
    setDraftFailed(false);
    setBusy("draft");
    let clipId = voice?.clipId ?? null;
    try {
      if (!clipId) clipId = (await voiceApi.uploadClip(audio.blob, audio.filename, "review", audio.source)).id;
      try {
        const transcription = await voiceApi.transcribe(clipId, language);
        setVoice({ clipId, transcriptionId: transcription.id });
        if (!transcription.no_speech) setText(transcription.text);
      } catch {
        setVoice({ clipId, transcriptionId: null });
        setDraftFailed(true); // typing still works
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
    try {
      const review = await bookingsApi.submitReview(booking.id, {
        rating, text: text.trim(),
        ...(voice ? { audio_clip_id: voice.clipId, ...(voice.transcriptionId ? { transcription_id: voice.transcriptionId } : {}) } : {}),
      });
      onDone(review);
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="review-form-heading" className="space-y-3 rounded-2xl border-2 border-primary bg-white p-4">
      <h2 id="review-form-heading" className="text-lg font-bold">{t("review.title")}</h2>
      <p className="text-sm">{t("review.intro")}</p>
      <StarPicker value={rating} onChange={setRating} />
      <details className="rounded-xl border border-line p-3">
        <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold"><Mic className="size-5" aria-hidden />{t("review.speak")}</summary>
        <div className="mt-3 space-y-3">
          <VoiceCapture audio={audio} onAudio={takeAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={busy !== null} />
          {audio && (
            <Button variant="secondary" loading={busy === "draft"} loadingLabel={t("conv.preparingCaption")} onClick={() => void draftFromVoice()}>
              {t("review.makeDraft")}
            </Button>
          )}
          {draftFailed && <Alert tone="warning">{t("review.draftFailed")}</Alert>}
        </div>
      </details>
      <TextArea label={t("review.textLabel")} hint={voice && !draftFailed ? t("review.checkDraft") : t("review.textHint")} value={text}
        onChange={setText} rows={3} maxLength={500} dir={text ? textDir(text) : language === "ur" ? "rtl" : "ltr"} />
      <p className="text-xs text-muted">{t("review.limits")}</p>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      <Button fullWidth loading={busy === "send"} loadingLabel={t("onboarding.saving")} disabled={rating === 0 || busy !== null}
        icon={<Send className="size-5" aria-hidden />} onClick={() => void send()}>
        {t("review.submit")}
      </Button>
    </section>
  );
}
