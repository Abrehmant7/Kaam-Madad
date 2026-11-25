import { CircleCheck, Keyboard, Mic, RefreshCw, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import * as catalogApi from "../api/catalog";
import * as voiceApi from "../api/voice";
import { useAuth } from "../auth/context";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { IconTileGroup } from "../components/ui/IconTile";
import { PageLoader } from "../components/ui/PageLoader";
import { TextArea } from "../components/ui/TextArea";
import { type CatalogData, DraftEditor } from "../features/voice/DraftEditor";
import { ReadAloud } from "../features/voice/ReadAloud";
import { SimulatedBadge } from "../features/voice/SimulatedBadge";
import { summaryText } from "../features/voice/summary";
import { type CapturedAudio, VoiceCapture } from "../features/voice/VoiceCapture";
import { useI18n } from "../i18n/context";
import { describeError, fieldErrorCodes, LocalMessage, translateFieldCodes } from "../i18n/errors";

type Busy = "transcribe" | "interpret" | "confirm" | null;

function changedFields(draft: voiceApi.DraftFields, edited: voiceApi.DraftFields): voiceApi.DraftFields {
  const changes: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(edited)) {
    if (JSON.stringify(value) !== JSON.stringify(draft[key as keyof voiceApi.DraftFields])) changes[key] = value;
  }
  return changes as voiceApi.DraftFields;
}

/**
 * Voice test: record or upload → replay → transcribe → review and correct → confirm →
 * read aloud. Exercises the real M3 endpoints. Everything the user has done (recording,
 * transcript, draft, edits) stays in this page's state when a request fails.
 */
export function VoiceTestPage() {
  const { t, language } = useI18n();
  const { user, config } = useAuth();
  const limits = config?.voice_limits ?? { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60, max_synthesis_chars: 1500 };
  const sttSimulated = Boolean(config?.ai?.speech_to_text.simulated);

  const [kind, setKind] = useState<voiceApi.VoiceKind>(user?.role === "customer" ? "job_description" : "worker_introduction");
  const [hint, setHint] = useState<voiceApi.LanguageHint>(language);
  const [mode, setMode] = useState<"voice" | "text">("voice");
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [clip, setClip] = useState<voiceApi.AudioClip | null>(null);
  const [transcription, setTranscription] = useState<voiceApi.Transcription | null>(null);
  const [typed, setTyped] = useState("");
  const [interpretation, setInterpretation] = useState<voiceApi.Interpretation | null>(null);
  const [fields, setFields] = useState<voiceApi.DraftFields>({});
  const [fieldErrorCodeMap, setFieldErrors] = useState<Record<string, string[]>>({});
  const fieldErrors = translateFieldCodes(fieldErrorCodeMap, t);
  // Errors are stored as objects/codes and translated at render (they follow a language switch).
  const [error, setError] = useState<{ step: Busy; failure: unknown } | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [catalog, setCatalog] = useState<CatalogData | null>(null);
  const [catalogError, setCatalogError] = useState<unknown>(null);
  const [catalogAttempt, setCatalogAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      catalogApi.fetchTrades(controller.signal),
      catalogApi.fetchAllServiceTags(controller.signal),
      catalogApi.fetchAreas(controller.signal),
    ])
      .then(([trades, services, areas]) => {
        if (!controller.signal.aborted) setCatalog({ trades: trades.results, services: services.results, areas: areas.results });
      })
      .catch((failure: unknown) => !controller.signal.aborted && setCatalogError(failure));
    return () => controller.abort();
  }, [catalogAttempt]);

  const onAudio = useCallback((next: CapturedAudio | null) => {
    setAudio(next);
    setClip(null); // a new recording must be uploaded again
    setTranscription(null);
    setError(null);
  }, []);

  function startDraft(next: voiceApi.Interpretation) {
    setInterpretation(next);
    setFields(next.effective_fields);
    setFieldErrors({});
  }

  async function runInterpretation(source: voiceApi.Transcription | null) {
    setBusy("interpret");
    setError(null);
    try {
      const next = source
        ? await voiceApi.interpretTranscription(kind, source.id, source.language)
        : await voiceApi.interpretText(kind, typed.trim(), hint);
      startDraft(next);
    } catch (failure) {
      setError({ step: "interpret", failure });
    } finally {
      setBusy(null);
    }
  }

  async function runTranscription() {
    if (!audio) return;
    setBusy("transcribe");
    setError(null);
    try {
      let uploaded = clip;
      if (!uploaded) {
        uploaded = await voiceApi.uploadClip(audio.blob, audio.filename, kind, audio.source);
        setClip(uploaded);
      }
      const result = await voiceApi.transcribe(uploaded.id, hint);
      setTranscription(result);
      setBusy(null);
      if (result.no_speech || !result.text.trim()) {
        setError({ step: "transcribe", failure: new LocalMessage("voice.noSpeech") });
        return;
      }
      await runInterpretation(result);
    } catch (failure) {
      setError({ step: "transcribe", failure });
      setBusy(null);
    }
  }

  async function confirm() {
    if (!interpretation) return;
    setBusy("confirm");
    setError(null);
    setFieldErrors({});
    try {
      const changes = changedFields(interpretation.draft.fields, fields);
      let current = interpretation;
      if (Object.keys(changes).length > 0) current = await voiceApi.saveCorrections(interpretation.id, changes);
      startDraft(await voiceApi.confirmInterpretation(current.id));
    } catch (failure) {
      setFieldErrors(fieldErrorCodes(failure, "fields."));
      setError({ step: "confirm", failure });
    } finally {
      setBusy(null);
    }
  }

  function restart() {
    setInterpretation(null);
    setFields({});
    setTranscription(null);
    setError(null);
  }

  if (!catalog) {
    return catalogError ? (
      <div className="space-y-3">
        <Alert tone="danger">{describeError(catalogError, t)}</Alert>
        <Button icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => { setCatalogError(null); setCatalogAttempt((n) => n + 1); }}>
          {t("common.retry")}
        </Button>
      </div>
    ) : (
      <PageLoader />
    );
  }

  const confirmed = interpretation?.confirmed ?? null;
  const locked = Boolean(confirmed) || busy !== null;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-primary">{t("voice.title")}</h1>
        <p className="text-muted">{t("voice.intro")}</p>
      </div>

      <IconTileGroup
        label={t("voice.kindLabel")}
        mode="single"
        options={[
          { value: "worker_introduction", label: t("voice.kind.worker_introduction"), icon: <Mic className="size-7" aria-hidden /> },
          { value: "job_description", label: t("voice.kind.job_description"), icon: <Mic className="size-7" aria-hidden /> },
        ]}
        value={[kind]}
        onChange={([value]) => {
          if (value && !locked) {
            setKind(value);
            restart();
            setClip(null);
          }
        }}
      />

      <IconTileGroup
        label={t("voice.languageLabel")}
        mode="single"
        options={[
          { value: "ur", label: "اردو", lang: "ur", icon: <span aria-hidden className="text-xl">ا</span> },
          { value: "en", label: "English", lang: "en", icon: <span aria-hidden className="text-xl">A</span> },
        ]}
        value={[hint]}
        onChange={([value]) => value && !locked && setHint(value)}
      />

      {/* Step 1: capture */}
      <section className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
        <h2 className="text-lg font-bold">{t("voice.step1")}</h2>
        <Alert tone={sttSimulated ? "demo" : "info"}>
          {sttSimulated ? t("voice.privacySimulated") : t("voice.privacyCloud")}
        </Alert>

        {mode === "voice" ? (
          <>
            <VoiceCapture
              audio={audio}
              onAudio={onAudio}
              maxSeconds={limits.max_audio_seconds}
              maxBytes={limits.max_audio_bytes}
              disabled={locked}
            />
            {audio && !interpretation && (
              <Button
                fullWidth
                loading={busy === "transcribe" || busy === "interpret"}
                loadingLabel={busy === "interpret" ? t("voice.interpreting") : t("voice.transcribing")}
                icon={<Send className="size-5" aria-hidden />}
                onClick={() => void runTranscription()}
              >
                {t("voice.transcribe")}
              </Button>
            )}
          </>
        ) : (
          <>
            <TextArea
              label={t("voice.typeLabel")}
              hint={t("voice.typeHint")}
              value={typed}
              onChange={setTyped}
              maxLength={4000}
              disabled={locked}
            />
            {!interpretation && (
              <Button
                fullWidth
                disabled={!typed.trim()}
                loading={busy === "interpret"}
                loadingLabel={t("voice.interpreting")}
                icon={<Send className="size-5" aria-hidden />}
                onClick={() => void runInterpretation(null)}
              >
                {t("voice.createDraft")}
              </Button>
            )}
          </>
        )}

        {!interpretation && (
          <Button
            variant="ghost"
            className="min-h-11 px-0"
            icon={mode === "voice" ? <Keyboard className="size-5" aria-hidden /> : <Mic className="size-5" aria-hidden />}
            onClick={() => setMode(mode === "voice" ? "text" : "voice")}
          >
            {mode === "voice" ? t("voice.typeInstead") : t("voice.speakInstead")}
          </Button>
        )}

        {error && (error.step === "transcribe" || error.step === "interpret") && (
          <Alert tone="danger" title={describeError(error.failure, t)}>
            <p>{t("voice.keptYourWork")}</p>
            {error.step === "interpret" && transcription && (
              <Button variant="ghost" className="min-h-11 px-0" icon={<RefreshCw className="size-4" aria-hidden />} onClick={() => void runInterpretation(transcription)}>
                {t("common.retry")}
              </Button>
            )}
          </Alert>
        )}
      </section>

      {/* Step 2: original transcript (read-only) */}
      {transcription && (
        <section className="space-y-2 rounded-2xl border border-line bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-bold">{t("voice.step2")}</h2>
            <SimulatedBadge show={transcription.simulated} />
          </div>
          <p className="text-sm text-muted">{t("voice.transcriptHelp")}</p>
          <blockquote dir="auto" className="rounded-xl bg-surface p-3">
            {transcription.text || "—"}
          </blockquote>
        </section>
      )}

      {/* Step 3: review and correct */}
      {interpretation && (
        <section className="space-y-4 rounded-2xl border border-line bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-bold">{t("voice.step3")}</h2>
            <SimulatedBadge show={interpretation.simulated} />
          </div>
          <p className="text-sm text-muted">{t("voice.reviewHelp")}</p>
          <DraftEditor
            kind={interpretation.kind}
            draft={interpretation.draft}
            fields={confirmed ? confirmed.fields : fields}
            onChange={setFields}
            catalog={catalog}
            errors={fieldErrors}
            disabled={locked}
          />
          {error?.step === "confirm" && <Alert tone="danger">{describeError(error.failure, t)}</Alert>}
          {!confirmed && (
            <Button
              fullWidth
              loading={busy === "confirm"}
              loadingLabel={t("voice.confirming")}
              icon={<CircleCheck className="size-5" aria-hidden />}
              onClick={() => void confirm()}
            >
              {t("voice.confirm")}
            </Button>
          )}
        </section>
      )}

      {/* Step 4: confirmed draft, read aloud */}
      {confirmed && (
        <section className="space-y-3 rounded-2xl border border-success/40 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-bold">{t("voice.step4")}</h2>
          <Alert tone="success">{t("voice.confirmedNotice")}</Alert>
          <ReadAloud text={summaryText(interpretation!.kind, confirmed.fields, catalog, t, language)} language={language} />
          <Button variant="secondary" icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => { restart(); setAudio(null); setClip(null); setTyped(""); }}>
            {t("voice.startOver")}
          </Button>
        </section>
      )}
    </div>
  );
}
