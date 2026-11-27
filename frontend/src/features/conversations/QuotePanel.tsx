import { CircleAlert, CircleCheck, FileText, PencilLine, RefreshCw, ShieldQuestion } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import * as convApi from "../../api/conversations";
import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { isTranslationKey, useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { textDir } from "../jobs/text";
import { formatDate, formatTime } from "../jobs/time";
import { ReadAloud } from "../voice/ReadAloud";
import { SimulatedBadge } from "../voice/SimulatedBadge";
import { LoadError } from "../worker/shared";
import { QuoteForm } from "./QuoteForm";
import { labourText, materialsText, money, quoteSpeech, visitText, windowText } from "./quoteText";

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{children}</dd>
    </div>
  );
}

/** The structured quote, identical for both parties. */
export function QuoteCard({ quote }: { quote: convApi.Quote }) {
  const { t, language } = useI18n();
  const when = windowText(quote, language);
  return (
    <dl className="space-y-3 rounded-2xl border border-line bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={quote.status === "submitted" && !quote.expired ? "info" : "neutral"}>
          {t("quote.versionLabel", { version: quote.version ?? "–" })} · {quote.expired && quote.status === "submitted" ? t("quote.status.expired") : t(`quote.status.${quote.status}`)}
        </StatusBadge>
        {quote.inspection_only && <StatusBadge tone="warning">{t("quote.form.inspection")}</StatusBadge>}
      </div>
      <Row title={t("quote.field.scope")}><span dir={textDir(quote.scope)} className="block whitespace-pre-line font-normal">{quote.scope || "—"}</span></Row>
      {quote.quantity != null && <Row title={t("quote.field.quantity")}><Ltr>{String(quote.quantity)}</Ltr></Row>}
      <Row title={t("quote.field.labour")}>{labourText(quote, t)}</Row>
      <Row title={t("quote.field.materials")}>{materialsText(quote, t)}</Row>
      <Row title={t("quote.field.visit")}>{visitText(quote, t)}</Row>
      {quote.exclusions && <Row title={t("quote.field.exclusions")}><span dir={textDir(quote.exclusions)} className="block font-normal">{quote.exclusions}</span></Row>}
      <Row title={t("quote.field.when")}>
        {when ? (
          <span className="flex flex-col">
            <span>{when.date}</span>
            <Ltr className="self-start">{when.time}</Ltr>
          </span>
        ) : "—"}
      </Row>
      {quote.totals && (
        <Row title={t("quote.field.total")}>
          <span className="flex flex-wrap items-center gap-1.5">
            <Ltr>{money(quote.totals.known_total) ?? ""}</Ltr>
            {!quote.totals.complete && <StatusBadge tone="warning">{t("quote.plusUnknown")}</StatusBadge>}
          </span>
        </Row>
      )}
      {quote.expires_at && quote.status === "submitted" && (
        <p className="text-sm text-muted">
          {t("quote.validUntil")} {formatDate(quote.expires_at, language)} <bdi dir="ltr">{formatTime(quote.expires_at, language)}</bdi>
        </p>
      )}
    </dl>
  );
}

function FindingItem({ finding, quote, invitationId, canAct, onChanged }: {
  finding: convApi.Finding; quote: convApi.Quote; invitationId: string; canAct: boolean; onChanged: () => void;
}) {
  const { t, language } = useI18n();
  const [resolution, setResolution] = useState<("clarified" | "not_a_conflict")[]>(["clarified"]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  // Rule findings have fixed wording (translated); checker findings keep the checker's own question.
  const ruleKey = `quote.finding.rule.${finding.code}`;
  const question = finding.source === "rule" && isTranslationKey(ruleKey) ? t(ruleKey) : finding.question;
  const kindKey = `quote.finding.code.${finding.code}`;
  const headline = finding.source === "ai" && isTranslationKey(kindKey) ? t(kindKey) : null;
  const stamp = (iso: string) => `${formatDate(iso, language)} ${formatTime(iso, language)}`;
  const sourceLabel = (source: convApi.Finding["sources"][number]) => {
    const materialsKey = `quote.materials.${source.text}`;
    if (source.kind === "quote" && source.ref === "materials" && isTranslationKey(materialsKey)) return t(materialsKey);
    if (source.kind === "quote" && source.ref === "materials_amount" && source.text === "unknown") return t("quote.unknown");
    if (source.ref === "window" || source.ref === "start_at") {
      const [from, to] = source.text.split(" – ");
      if (from && to && !Number.isNaN(Date.parse(from)) && !Number.isNaN(Date.parse(to))) return `${stamp(from)} – ${formatTime(to, language)}`;
    }
    return source.text;
  };

  async function resolve() {
    setFailure(null);
    setBusy(true);
    try {
      await convApi.resolveFinding(invitationId, quote.id, finding.id, resolution[0] ?? "clarified", note.trim());
      onChanged();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 rounded-xl border border-warning/50 bg-warning-soft p-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={finding.status === "open" ? (finding.blocking ? "danger" : "warning") : "success"}>
          {finding.status === "open" ? (finding.blocking ? t("quote.finding.needsClarification") : t("quote.finding.note")) : t("quote.finding.resolved")}
        </StatusBadge>
        <StatusBadge tone="neutral">{finding.source === "ai" ? t("quote.finding.fromCheck") : t("quote.finding.fromRules")}</StatusBadge>
      </div>
      {headline && <p className="text-sm font-bold">{headline}</p>}
      <p className="font-bold" dir={textDir(question)}>{question}</p>
      <p className="text-sm">{t(`quote.finding.ask.${finding.ask}`)}</p>
      <ul className="space-y-1 text-sm">
        {finding.sources.map((source) => (
          <li key={`${source.kind}-${source.ref}-${source.text}`} className="rounded-lg bg-white p-2">
            <span className="font-bold">{t(`quote.source.${source.kind}`)}: </span>
            <bdi dir={textDir(sourceLabel(source))}>“{sourceLabel(source)}”</bdi>
          </li>
        ))}
      </ul>
      {finding.status === "resolved" ? (
        <p className="text-sm">
          {t(`quote.resolution.${finding.resolution ?? "clarified"}`)} ({t(`conv.role.${finding.resolved_role ?? "customer"}`)}): <span dir={textDir(finding.resolution_note ?? "")}>{finding.resolution_note}</span>
        </p>
      ) : (
        canAct && (
          <div className="space-y-2">
            <IconTileGroup label={t("quote.resolution.label")} mode="single" columns={1} value={resolution} onChange={setResolution}
              options={[{ value: "clarified", label: t("quote.resolution.clarified"), icon: <CircleCheck className="size-5" aria-hidden /> },
                        { value: "not_a_conflict", label: t("quote.resolution.not_a_conflict"), icon: <ShieldQuestion className="size-5" aria-hidden /> }]} />
            <TextArea label={t("quote.resolution.noteLabel")} hint={t("quote.resolution.noteHint")} value={note} onChange={setNote} rows={2} maxLength={500} dir={note ? textDir(note) : "auto"} />
            {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
            <Button variant="secondary" loading={busy} loadingLabel={t("onboarding.saving")} disabled={note.trim().length < 3} onClick={() => void resolve()}>
              {t("quote.resolution.save")}
            </Button>
          </div>
        )
      )}
    </li>
  );
}

const QUOTE_POLL_MS = 15000;

/** Load the quotes and refresh them quietly: the worker's open form and typed notes are never unmounted. */
function useQuotes(invitationId: string, refreshKey: number) {
  const [listing, setListing] = useState<convApi.QuotesListing | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      convApi.fetchQuotes(invitationId, controller.signal)
        .then((next) => { setListing(next); setError(null); })
        .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure); });
    void load();
    const timer = window.setInterval(() => void load(), QUOTE_POLL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [invitationId, refreshKey, attempt]);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { listing, error, reload };
}

/** Quotes for one invitation: current version, findings, readiness, history, and the worker's form. */
export function QuotePanel({ invitationId, role, canWrite, refreshKey }: { invitationId: string; role: "customer" | "worker"; canWrite: boolean; refreshKey: number }) {
  const { t, language } = useI18n();
  const data = useQuotes(invitationId, refreshKey);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<"check" | "manual" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);

  if (!data.listing) return data.error ? <LoadError error={data.error} onRetry={data.reload} /> : <PageLoader />;
  const { current, draft, history, readiness } = data.listing;

  async function act(kind: "check" | "manual") {
    if (!current) return;
    setFailure(null);
    setBusy(kind);
    try {
      if (kind === "check") await convApi.rerunCheck(invitationId, current.id);
      else await convApi.manualReview(invitationId, current.id);
      data.reload();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  const reason = (code: string) => (isTranslationKey(`quote.blocking.${code}`) ? t(`quote.blocking.${code}` as never) : code);

  return (
    <section aria-labelledby="quote-heading" className="space-y-3">
      <h2 id="quote-heading" className="flex items-center gap-2 text-lg font-bold">
        <FileText className="size-5" aria-hidden />
        {t("quote.title")}
      </h2>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      {current ? (
        <>
          {readiness.ready ? (
            <Alert tone="success" title={t("quote.ready.title")}>
              <p>{t("quote.ready.body", { version: readiness.version ?? "" })}</p>
              {readiness.warnings.map((code) => (
                <p key={code} className="text-sm">{isTranslationKey(`quote.warning.${code}`) ? t(`quote.warning.${code}` as never) : code}</p>
              ))}
            </Alert>
          ) : (
            <Alert tone="warning" title={t("quote.notReady.title")}>
              <ul className="list-inside list-disc">
                {readiness.blocking.map((code) => (
                  <li key={code}>{reason(code)}</li>
                ))}
              </ul>
            </Alert>
          )}
          <QuoteCard quote={current} />
          <ReadAloud text={quoteSpeech(current, language, t)} language={language} />

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-bold">{t("quote.check.label")}:</span>
            <StatusBadge tone={current.check.status === "passed" ? "success" : current.check.status === "findings" ? "warning" : "neutral"}>
              {t(`quote.check.${current.check.status}`)}
            </StatusBadge>
            <SimulatedBadge show={current.check.simulated} />
          </div>
          {current.check.status === "passed" && <p className="text-sm text-muted">{t("quote.check.passedNote")}</p>}
          {current.check.status === "unavailable" && (
            <Alert tone="warning" title={t("quote.check.unavailableTitle")}>
              <p>{t("quote.check.unavailableBody")}</p>
              {current.manual_review_at && <p className="font-bold">{t("quote.check.manualDone")}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                {canWrite && (
                  <Button variant="secondary" loading={busy === "check"} loadingLabel={t("onboarding.saving")} icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => void act("check")}>
                    {t("quote.check.retry")}
                  </Button>
                )}
                {canWrite && role === "customer" && !current.manual_review_at && (
                  <Button variant="secondary" loading={busy === "manual"} loadingLabel={t("onboarding.saving")} icon={<CircleCheck className="size-5" aria-hidden />} onClick={() => void act("manual")}>
                    {t("quote.check.manualReview")}
                  </Button>
                )}
              </div>
            </Alert>
          )}
          {current.findings.length > 0 && (
            <ul className="space-y-2">
              {current.findings.map((finding) => (
                <FindingItem key={finding.id} finding={finding} quote={current} invitationId={invitationId} canAct={canWrite} onChanged={data.reload} />
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="text-muted">{role === "worker" ? t("quote.none.worker") : t("quote.none.customer")}</p>
      )}

      {role === "worker" && canWrite && !editing && (
        <Button variant={current ? "secondary" : "primary"} fullWidth icon={<PencilLine className="size-5" aria-hidden />} onClick={() => setEditing(true)}>
          {draft ? t("quote.continueDraft") : current ? t("quote.revise") : t("quote.create")}
        </Button>
      )}
      {editing && canWrite && (
        <QuoteForm invitationId={invitationId} start={draft ?? current} onDone={() => { setEditing(false); data.reload(); }} />
      )}

      {history.length > 0 && (
        <details className="rounded-2xl border border-line bg-surface p-3">
          <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold">
            <CircleAlert className="size-5" aria-hidden />
            {t("quote.history", { count: history.length })}
          </summary>
          <div className="mt-3 space-y-3">
            {history.map((quote) => (
              <QuoteCard key={quote.id} quote={quote} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
