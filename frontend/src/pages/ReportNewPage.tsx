import { Flag, ImagePlus, Send } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import * as reportsApi from "../api/reports";
import * as voiceApi from "../api/voice";
import { useAuth } from "../auth/context";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { IconTileGroup } from "../components/ui/IconTile";
import { TextArea } from "../components/ui/TextArea";
import { textDir } from "../features/jobs/text";
import { type CapturedAudio, VoiceCapture } from "../features/voice/VoiceCapture";
import { useI18n } from "../i18n/context";
import { describeError } from "../i18n/errors";

const CATEGORIES: reportsApi.ReportCategory[] = ["harassment", "threats", "impersonation", "no_show", "property_work", "other"];
const DEFAULT_LIMITS = { max_audio_bytes: 10 * 1024 * 1024, max_audio_seconds: 60 };
const MAX_FILES = 5;

/** File a private report about the other participant of an invitation or booking (REP-01). */
export function ReportNewPage() {
  const { t, language } = useI18n();
  const { config } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const invitationId = params.get("invitation");
  const bookingId = params.get("booking");
  const limits = config?.voice_limits ?? DEFAULT_LIMITS;
  const [category, setCategory] = useState<reportsApi.ReportCategory[]>([]);
  const [description, setDescription] = useState("");
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [partial, setPartial] = useState<string | null>(null);
  const clientId = useRef(crypto.randomUUID()); // kept for retries: the same report is never filed twice
  const clipId = useRef<string | null>(null);
  const takeAudio = useCallback((next: CapturedAudio | null) => { setAudio(next); clipId.current = null; }, []);

  if (!invitationId && !bookingId) return <Alert tone="danger">{t("errors.not_found")}</Alert>;
  const ready = category.length === 1 && (description.trim().length > 0 || audio !== null);

  async function submit() {
    setFailure(null);
    setBusy(true);
    try {
      if (audio && !clipId.current) clipId.current = (await voiceApi.uploadClip(audio.blob, audio.filename, "report", audio.source)).id;
      const report = await reportsApi.fileReport({
        client_id: clientId.current, category: category[0]!, description: description.trim(),
        ...(invitationId ? { invitation_id: invitationId } : { booking_id: bookingId! }),
        ...(clipId.current ? { audio_clip_id: clipId.current } : {}),
      });
      let failed = 0;
      for (const file of files) {
        try {
          await reportsApi.addImageEvidence(report.id, file, file.name);
        } catch {
          failed += 1; // the report itself is filed; the reporter can add evidence again from its page
        }
      }
      if (failed) {
        setPartial(report.id);
        return;
      }
      navigate(`/reports/${report.id}`);
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-ink sm:text-3xl">
        <Flag className="size-7" aria-hidden />
        {t("report.new.title")}
      </h1>
      <Alert tone="info" title={t("report.new.privateTitle")}>
        <p>{t("report.new.privateBody")}</p>
        <p className="mt-1 text-sm">{t("report.new.notEmergency")}</p>
      </Alert>
      <IconTileGroup label={t("report.categoryLabel")} mode="single" columns={1} value={category} onChange={setCategory}
        options={CATEGORIES.map((value) => ({ value, label: t(`report.category.${value}`), icon: <Flag className="size-5" aria-hidden /> }))} />
      <TextArea label={t("report.descriptionLabel")} hint={t("report.descriptionHint")} value={description} onChange={setDescription}
        rows={4} maxLength={2000} dir={description ? textDir(description) : language === "ur" ? "rtl" : "ltr"} />
      <section className="space-y-2 rounded-2xl border border-line bg-white p-3">
        <h2 className="font-bold">{t("report.voiceTitle")}</h2>
        <p className="text-sm text-muted">{t("report.voiceHint")}</p>
        <VoiceCapture audio={audio} onAudio={takeAudio} maxSeconds={limits.max_audio_seconds} maxBytes={limits.max_audio_bytes} disabled={busy} />
      </section>
      <section className="space-y-2 rounded-2xl border border-line bg-white p-3">
        <h2 className="flex items-center gap-2 font-bold"><ImagePlus className="size-5" aria-hidden />{t("report.evidenceTitle")}</h2>
        <p className="text-sm text-muted">{t("report.evidenceHint")}</p>
        <input type="file" accept="image/jpeg,image/png,image/webp" multiple aria-label={t("report.evidenceTitle")} disabled={busy}
          className="block w-full text-sm" onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, MAX_FILES))} />
        {files.length > 0 && <p className="text-sm">{t("report.filesChosen", { count: files.length })}</p>}
      </section>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      {partial && (
        <Alert tone="warning" title={t("report.partialTitle")}>
          <p>{t("report.partialBody")}</p>
          <Button variant="secondary" className="mt-2" onClick={() => navigate(`/reports/${partial}`)}>{t("report.open")}</Button>
        </Alert>
      )}
      <Button fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={!ready || busy || partial !== null}
        icon={<Send className="size-5" aria-hidden />} onClick={() => void submit()}>
        {t("report.submit")}
      </Button>
    </div>
  );
}
