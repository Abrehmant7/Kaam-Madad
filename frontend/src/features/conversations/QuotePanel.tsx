import { CalendarCheck, CircleAlert, CircleCheck, FileText, History, LoaderCircle, MessagesSquare, PencilLine, RefreshCw } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import * as convApi from "../../api/conversations";
import type { BookingTerms } from "../../api/bookings";
import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { isTranslationKey, useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { readDraft } from "../drafts";
import { stagePath } from "../jobs/JobStages";
import { textDir } from "../jobs/text";
import { formatDate, formatTime } from "../jobs/time";
import { ReadAloud } from "../voice/ReadAloud";
import { SimulatedBadge } from "../voice/SimulatedBadge";
import { LoadError } from "../worker/shared";
import { AcceptQuote } from "../bookings/AcceptQuote";
import { QuoteForm, quoteFormDraftKey } from "./QuoteForm";
import { labourText, materialsText, money, quoteSpeech, visitText, windowText } from "./quoteText";


function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{children}</dd>
    </div>
  );
}

/** The structured terms rows (scope, labour, materials, fees, time, known total) — quotes and bookings alike. */
export function TermsRows({ quote }: { quote: convApi.QuoteTerms & { totals: convApi.Quote["totals"] | BookingTerms["totals"] } }) {
  const { t, language } = useI18n();
  const when = windowText(quote, language);
  return (
    <>
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
    </>
  );
}

/** The structured quote, identical for both parties. */
export function QuoteCard({ quote }: { quote: convApi.Quote }) {
  const { t, language } = useI18n();
  return (
    <dl className="space-y-3 card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={quote.status === "submitted" && !quote.expired ? "info" : "neutral"}>
          {t("quote.versionLabel", { version: quote.version ?? "–" })} · {quote.expired && quote.status === "submitted" ? t("quote.status.expired") : t(`quote.status.${quote.status}`)}
        </StatusBadge>
        {quote.inspection_only && <StatusBadge tone="warning">{t("quote.form.inspection")}</StatusBadge>}
      </div>
      <TermsRows quote={quote} />
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
  const [resolution, setResolution] = useState<convApi.Resolution[]>(["terms_confirmed"]);
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
      await convApi.resolveFinding(invitationId, quote.id, finding.id, resolution[0] ?? "terms_confirmed", note.trim());
      onChanged();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 rounded-xl border border-warning/50 bg-warning-soft p-3">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusBadge tone={finding.status === "open" ? (finding.blocking ? "danger" : "warning") : "success"}>
          {finding.status === "open" ? (finding.blocking ? t("quote.finding.needsClarification") : t("quote.finding.note")) : t("quote.finding.resolved")}
        </StatusBadge>
        <span className="text-xs text-muted">{finding.source === "ai" ? t("quote.finding.fromCheck") : t("quote.finding.fromRules")}</span>
      </p>
      {headline && <p className="text-sm font-bold">{headline}</p>}
      <p className="font-bold" dir={textDir(question)}>{question}</p>
      <p className="text-sm">{t(`quote.finding.ask.${finding.ask}`)}</p>
      {finding.sources.length > 0 && (
        <details className="text-sm">
          <summary className="flex min-h-11 cursor-pointer items-center font-bold text-primary">{t("quote.finding.showSources", { count: finding.sources.length })}</summary>
          <ul className="mt-1 space-y-1">
            {finding.sources.map((source) => (
              <li key={`${source.kind}-${source.ref}-${source.text}`} className="rounded-lg bg-white p-2">
                <span className="font-bold">{t(`quote.source.${source.kind}`)}: </span>
                <bdi dir={textDir(sourceLabel(source))}>“{sourceLabel(source)}”</bdi>
              </li>
            ))}
          </ul>
        </details>
      )}
      {finding.status === "resolved" ? (
        <div className="space-y-1 text-sm">
          <p>
            {t(`quote.resolution.${finding.resolution ?? "terms_confirmed"}`)} ({t(`conv.role.${finding.resolved_role ?? "customer"}`)}): <span dir={textDir(finding.resolution_note ?? "")}>{finding.resolution_note}</span>
          </p>
          {finding.resolution === "terms_changed" && <StatusBadge tone="warning">{t("quote.resolution.revisionNeeded")}</StatusBadge>}
        </div>
      ) : (
        canAct && (
          <div className="space-y-2">
            <IconTileGroup label={t("quote.resolution.label")} mode="single" columns={1} value={resolution} onChange={setResolution}
              options={[{ value: "terms_confirmed", label: t("quote.resolution.terms_confirmed"), icon: <CircleCheck className="size-5" aria-hidden /> },
                        { value: "terms_changed", label: t("quote.resolution.terms_changed"), icon: <PencilLine className="size-5" aria-hidden /> }]} />
            <p className="text-sm text-muted">{resolution[0] === "terms_changed" ? t("quote.resolution.changedHint") : t("quote.resolution.confirmedHint")}</p>
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
const RUNNING_POLL_MS = 3000;

/** Load the quotes and refresh them quietly: the worker's open form and typed notes are never unmounted. Called
 * once by the conversation layout and shared by the chat and quote screens and the stage header: a single poll. */
export function useQuotes(invitationId: string, refreshKey: number) {
  const [listing, setListing] = useState<convApi.QuotesListing | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const running = listing?.current?.check.status === "running";
  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      convApi.fetchQuotes(invitationId, controller.signal)
        .then((next) => { setListing(next); setError(null); })
        .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure); });
    void load();
    const timer = window.setInterval(() => void load(), running ? RUNNING_POLL_MS : QUOTE_POLL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [invitationId, refreshKey, attempt, running]);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { listing, error, reload };
}

export type QuotesState = ReturnType<typeof useQuotes>;

function Fact({ title, children, wide = false }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`min-w-0 rounded-xl border border-line bg-[#fbfcff] p-3 ${wide ? "sm:col-span-2" : ""}`}>
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{children}</dd>
    </div>
  );
}

/** What both people agree on first: the known total, who provides the materials, the work and the appointment. */
export function QuoteFacts({ quote, withTime = true }: {
  quote: convApi.QuoteTerms & { totals: convApi.Quote["totals"] | BookingTerms["totals"] };
  /** False where the booked time is already shown (Work progress). */
  withTime?: boolean;
}) {
  const { t, language } = useI18n();
  const when = windowText(quote, language);
  return (
    <dl className="grid gap-2 sm:grid-cols-2">
      <div className="rounded-xl bg-primary-soft p-3 sm:col-span-2">
        <dt className="text-sm text-[#233f80]">{t("quote.field.total")}</dt>
        <dd className="flex flex-wrap items-baseline gap-x-2">
          <Ltr className="text-2xl font-bold text-ink">{money(quote.totals?.known_total) ?? "—"}</Ltr>
          {quote.totals && !quote.totals.complete && <span className="text-sm font-bold text-warning-strong">{t("quote.plusUnknown")}</span>}
        </dd>
      </div>
      <Fact title={t("quote.field.materials")} wide={!withTime}>{materialsText(quote, t)}</Fact>
      {withTime && (
        <Fact title={t("quote.field.when")}>
          {when ? <span className="flex flex-wrap gap-x-2"><span>{when.date}</span><Ltr>{when.time}</Ltr></span> : "—"}
        </Fact>
      )}
      <Fact title={t("quote.field.scope")} wide>
        <span dir={textDir(quote.scope)} className="block whitespace-pre-line font-normal">{quote.scope || "—"}</span>
      </Fact>
    </dl>
  );
}

function CheckLine({ quote }: { quote: convApi.Quote }) {
  const { t } = useI18n();
  return (
    <div className="space-y-1 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <span className="font-bold">{t("quote.check.label")}:</span>
        <StatusBadge tone={quote.check.status === "passed" ? "success" : quote.check.status === "findings" ? "warning" : "neutral"}
          icon={quote.check.status === "running" ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : undefined}>
          {t(`quote.check.${quote.check.status}`)}
        </StatusBadge>
        <SimulatedBadge show={quote.check.simulated} />
      </p>
      {quote.check.status === "passed" && <p className="text-muted">{t("quote.check.passedNote")}</p>}
      {quote.check.status === "running" && <p className="text-muted" role="status">{t("quote.check.runningNote")}</p>}
    </div>
  );
}

/**
 * The quote screen for one invitation (both roles). The terms that matter come first; beside them the one next
 * action for this person: accept, revise, clarify, retry the check or confirm it manually. A blocking agreement issue
 * sits with that action, with the source statements it came from. Full terms and earlier versions are secondary.
 * Workers write and revise on this screen (`?edit=1`), next to the customer's request (`brief`).
 */
export function QuotePanel({ invitationId, role, canWrite: open, data, booked, bookingId = null, brief }: {
  invitationId: string; role: "customer" | "worker"; canWrite: boolean; data: QuotesState; booked: boolean;
  bookingId?: string | null; brief?: ReactNode;
}) {
  const { t, language } = useI18n();
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState<"check" | "manual" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);

  if (!data.listing) return data.error ? <LoadError error={data.error} onRetry={data.reload} /> : <PageLoader />;
  const { current, draft, history, readiness } = data.listing;
  // After acceptance the quote and its approval record stay as they were: no edits, resolutions or checks.
  const isBooked = booked || Boolean(readiness.booking_id);
  const workId = bookingId ?? readiness.booking_id;
  const canWrite = open && !isBooked;
  const editing = role === "worker" && canWrite && params.get("edit") === "1";
  const localDraft = readDraft(quoteFormDraftKey(invitationId)) !== undefined;
  const setEditing = (on: boolean) => setParams(on ? { edit: "1" } : {}, { replace: true });

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
  const backToChat = (
    <ButtonLink to={stagePath.chat(invitationId)} variant="ghost" fullWidth icon={<MessagesSquare className="size-5" aria-hidden />}>
      {t("quote.backToChat")}
    </ButtonLink>
  );

  if (editing) {
    return (
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)]">
        <div className="min-w-0">
          <QuoteForm invitationId={invitationId} start={draft ?? current} onDone={() => { setEditing(false); data.reload(); }} onCancel={() => setEditing(false)} />
        </div>
        <aside aria-label={t("quote.requestAside")} className="min-w-0 space-y-3 lg:sticky lg:top-24">
          {brief}
          {backToChat}
        </aside>
      </div>
    );
  }

  const openFindings = current ? current.findings.filter((finding) => finding.status === "open") : [];
  const settled = current ? current.findings.filter((finding) => finding.status !== "open") : [];
  const workerEdit = role === "worker" && canWrite && (
    <Button variant={current && readiness.ready ? "secondary" : "primary"} fullWidth icon={<PencilLine className="size-5" aria-hidden />} onClick={() => setEditing(true)}>
      {draft || localDraft ? t("quote.continueDraft") : current ? t("quote.revise") : t("quote.create")}
    </Button>
  );

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,26rem)] lg:grid-rows-[auto_1fr]">
      <section aria-labelledby="quote-heading" className="card min-w-0 space-y-4 p-4 sm:p-5 lg:col-start-1 lg:row-start-1">
        {current ? (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <h2 id="quote-heading" className="flex items-center gap-2 text-lg font-bold">
                <FileText className="size-5 text-primary" aria-hidden />
                {t("quote.versionLabel", { version: current.version ?? "–" })}
                {current.inspection_only && <StatusBadge tone="warning">{t("quote.form.inspection")}</StatusBadge>}
              </h2>
              {current.expires_at && current.status === "submitted" && !isBooked && (
                <p className="text-sm text-muted">
                  {current.expired ? t("quote.status.expired") : <>{t("quote.validUntil")} {formatDate(current.expires_at, language)} <bdi dir="ltr">{formatTime(current.expires_at, language)}</bdi></>}
                </p>
              )}
            </div>
            <QuoteFacts quote={current} />
            <ReadAloud text={quoteSpeech(current, language, t)} language={language} showText={false} />
          </>
        ) : (
          <>
            <h2 id="quote-heading" className="flex items-center gap-2 text-lg font-bold">
              <FileText className="size-5 text-primary" aria-hidden />
              {t("quote.title")}
            </h2>
            <p className="text-muted">{role === "worker" ? t("quote.none.worker") : t("quote.none.customer")}</p>
          </>
        )}
      </section>

      <aside aria-label={t("quote.nextAction")} className="min-w-0 space-y-3 lg:sticky lg:top-24 lg:col-start-2 lg:row-span-2 lg:row-start-1">
        <div className="card-action space-y-3 p-4">
          {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
          {isBooked ? (
            <>
              <p className="flex items-center gap-2 font-bold text-success-strong"><CircleCheck className="size-5" aria-hidden />{t("quote.accepted.title")}</p>
              <p className="text-sm">{t("quote.accepted.body")}</p>
              {workId && (
                <ButtonLink to={stagePath.work(workId)} fullWidth icon={<CalendarCheck className="size-5" aria-hidden />}>{t("stage.openWork")}</ButtonLink>
              )}
            </>
          ) : !current ? (
            role === "worker" ? (canWrite ? workerEdit : <p className="text-sm">{t("conv.closed")}</p>) : <p className="font-bold">{t("quote.waiting")}</p>
          ) : (
            <>
              {readiness.ready ? (
                <div className="space-y-1">
                  <p className="flex items-center gap-2 font-bold text-success-strong"><CircleCheck className="size-5" aria-hidden />{t("quote.ready.title")}</p>
                  {readiness.warnings.map((code) => (
                    <p key={code} className="text-sm">{isTranslationKey(`quote.warning.${code}`) ? t(`quote.warning.${code}` as never) : code}</p>
                  ))}
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="flex items-center gap-2 font-bold text-warning-strong"><CircleAlert className="size-5" aria-hidden />{t("quote.notReady.title")}</p>
                  <ul className="list-inside list-disc text-sm">
                    {readiness.blocking.map((code) => <li key={code}>{reason(code)}</li>)}
                  </ul>
                </div>
              )}
              {openFindings.length > 0 && (
                <ul className="space-y-2">
                  {openFindings.map((finding) => (
                    <FindingItem key={finding.id} finding={finding} quote={current} invitationId={invitationId} canAct={canWrite} onChanged={data.reload} />
                  ))}
                </ul>
              )}
              {current.check.status === "unavailable" && (
                <Alert tone="warning" title={t("quote.check.unavailableTitle")}>
                  <p>{current.check.failure === "stalled" ? t("quote.check.stalledBody") : t("quote.check.unavailableBody")}</p>
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
              {role === "customer" && readiness.ready && canWrite && (
                <AcceptQuote invitationId={invitationId} quote={current} onStale={data.reload} />
              )}
              {role === "customer" && !readiness.ready && <p className="text-sm text-muted">{t("quote.customerWait")}</p>}
              {workerEdit}
            </>
          )}
          {backToChat}
        </div>
        {current && <CheckLine quote={current} />}
      </aside>

      {current && (
        <div className="min-w-0 space-y-3 lg:col-start-1 lg:row-start-2">
          <details className="card p-3 sm:px-4">
            <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold">
              <FileText className="size-5" aria-hidden />
              {t("quote.fullTerms")}
            </summary>
            <div className="mt-3"><QuoteCard quote={current} /></div>
          </details>
          {settled.length > 0 && (
            <details className="card p-3 sm:px-4">
              <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold">
                <CircleCheck className="size-5" aria-hidden />
                {t("quote.settled", { count: settled.length })}
              </summary>
              <ul className="mt-3 space-y-2">
                {settled.map((finding) => (
                  <FindingItem key={finding.id} finding={finding} quote={current} invitationId={invitationId} canAct={false} onChanged={data.reload} />
                ))}
              </ul>
            </details>
          )}
          {history.length > 0 && (
            <details className="card p-3 sm:px-4">
              <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold">
                <History className="size-5" aria-hidden />
                {t("quote.history", { count: history.length })}
              </summary>
              <div className="mt-3 space-y-3">
                {history.map((quote) => (
                  <QuoteCard key={quote.id} quote={quote} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
