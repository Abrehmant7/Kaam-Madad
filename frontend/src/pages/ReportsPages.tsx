import { ArrowLeft, FileWarning, ImagePlus, Paperclip, Send } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import * as reportsApi from "../api/reports";
import { useAuth } from "../auth/context";
import { Alert } from "../components/ui/Alert";
import { Button, ButtonLink } from "../components/ui/Button";
import { PageLoader } from "../components/ui/PageLoader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { TextArea } from "../components/ui/TextArea";
import { textDir } from "../features/jobs/text";
import { formatDate, formatTime } from "../features/jobs/time";
import { LoadError, useLoad } from "../features/worker/shared";
import { useI18n } from "../i18n/context";
import { describeError } from "../i18n/errors";

export const REPORT_TONE = { open: "warning", reviewing: "info", resolved: "success", dismissed: "neutral" } as const;

function Stamp({ iso }: { iso: string }) {
  const { language } = useI18n();
  return <span>{formatDate(iso, language)} <bdi dir="ltr">{formatTime(iso, language)}</bdi></span>;
}

/** "My reports": only reports I filed. */
export function ReportsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const data = useLoad((signal) => reportsApi.listReports(signal), []);
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const reports = data.state.data.results;
  return (
    <div className="space-y-5">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-ink sm:text-3xl"><FileWarning className="size-7" aria-hidden />{t("report.mine")}</h1>
      <p className="text-sm text-muted">{t("report.mineNote")}</p>
      {reports.length === 0 ? (
        <p className="text-muted">{t("report.none")}</p>
      ) : (
        <ul className="space-y-3">
          {reports.map((report) => (
            <li key={report.id} className="space-y-2 rounded-2xl border border-line bg-white p-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={REPORT_TONE[report.status]}>{t(`report.status.${report.status}`)}</StatusBadge>
                {report.awaiting_reply && <StatusBadge tone="warning">{t("report.needsReply")}</StatusBadge>}
              </div>
              <p className="font-bold">{t(`report.category.${report.category}`)}</p>
              <p className="text-sm text-muted"><Stamp iso={report.created_at} /></p>
              <Link to={`/reports/${report.id}`} className="inline-flex min-h-11 items-center font-bold text-primary underline">{t("report.open")}</Link>
            </li>
          ))}
        </ul>
      )}
      <ButtonLink to={user?.role === "worker" ? "/worker" : "/customer"} variant="secondary" fullWidth
        icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("conv.back")}
      </ButtonLink>
    </div>
  );
}

function EvidenceItem({ item }: { item: reportsApi.ReportEvidence }) {
  const { t } = useI18n();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  if (item.removed || !item.content_url) return <li className="text-sm text-muted">{t("report.evidenceRemoved")}</li>;
  async function open() {
    try {
      setUrl(URL.createObjectURL(await reportsApi.fetchEvidence(item.content_url!)));
    } catch {
      setFailed(true);
    }
  }
  return (
    <li className="space-y-2 rounded-xl border border-line p-2 text-sm">
      <p className="flex items-center gap-2"><Paperclip className="size-4" aria-hidden />
        {item.role === "statement" ? t("report.voiceStatement") : t(`report.evidenceKind.${item.kind}`)}</p>
      {url ? (item.kind === "image" ? <img src={url} alt={t("report.evidenceKind.image")} className="max-h-60 rounded-lg" />
        : <audio controls src={url} className="w-full" />) : (
        <Button variant="ghost" onClick={() => void open()}>{t("report.viewEvidence")}</Button>
      )}
      {failed && <p className="text-danger-strong">{t("audio.failed")}</p>}
    </li>
  );
}

/** One of my reports: status, what staff told me, my replies; never internal notes. */
export function ReportDetailPage() {
  const { id = "" } = useParams();
  const { t } = useI18n();
  const data = useLoad((signal) => reportsApi.fetchReport(id, signal), [id]);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const report = data.state.data;

  async function run(action: () => Promise<reportsApi.Report>, after?: () => void) {
    setFailure(null);
    setBusy(true);
    try {
      data.set(await action());
      after?.();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("report.title")}</h1>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={REPORT_TONE[report.status]}>{t(`report.status.${report.status}`)}</StatusBadge>
        <span className="font-bold">{t(`report.category.${report.category}`)}</span>
      </div>
      <p className="text-sm text-muted">{t(`report.statusExplain.${report.status}`)}</p>
      {report.awaiting_reply && <Alert tone="warning" title={t("report.needsReply")}>{t("report.needsReplyBody")}</Alert>}
      {report.description && (
        <section className="rounded-2xl border border-line bg-white p-3">
          <h2 className="text-sm text-muted">{t("report.descriptionLabel")}</h2>
          <p dir={textDir(report.description)} className="whitespace-pre-line">{report.description}</p>
        </section>
      )}
      {report.evidence.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-bold">{t("report.evidenceList")}</h2>
          <ul className="space-y-2">{report.evidence.map((item) => <EvidenceItem key={item.id} item={item} />)}</ul>
        </section>
      )}
      {report.can_add_evidence && (
        <label className="flex min-h-11 cursor-pointer items-center gap-2 font-bold text-primary">
          <ImagePlus className="size-5" aria-hidden />{t("report.addEvidence")}
          <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" disabled={busy}
            onChange={(e) => { const file = e.target.files?.[0]; if (file) void run(() => reportsApi.addImageEvidence(report.id, file, file.name)); }} />
        </label>
      )}
      <section aria-labelledby="updates-heading" className="space-y-2">
        <h2 id="updates-heading" className="font-bold">{t("report.updates")}</h2>
        {report.messages.length === 0 ? <p className="text-sm text-muted">{t("report.noUpdates")}</p> : (
          <ol className="space-y-2">
            {report.messages.map((message, index) => (
              <li key={index} className={`rounded-xl border p-3 text-sm ${message.from === "staff" ? "border-primary/40 bg-primary/5" : "border-line bg-white"}`}>
                <p className="font-bold">{message.from === "staff" ? t("report.fromStaff") : t("conv.you")} · <Stamp iso={message.at} /></p>
                <p dir={textDir(message.text)} className="whitespace-pre-line">{message.text}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
      {report.can_reply && (
        <section className="space-y-2">
          <TextArea label={t("report.replyLabel")} value={reply} onChange={setReply} rows={3} maxLength={2000} dir={reply ? textDir(reply) : "auto"} />
          <Button fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={reply.trim().length < 2}
            icon={<Send className="size-5" aria-hidden />} onClick={() => void run(() => reportsApi.replyToReport(report.id, reply.trim()), () => setReply(""))}>
            {t("report.sendReply")}
          </Button>
        </section>
      )}
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      <ButtonLink to="/reports" variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
        {t("report.mine")}
      </ButtonLink>
    </div>
  );
}
