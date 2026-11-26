import { ArrowLeft, Camera, CircleCheck, CircleDashed, CircleX, RotateCcw, Send, ShieldCheck, Upload } from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import * as workersApi from "../../api/workers";
import { PATHS } from "../../auth/paths";
import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextField } from "../../components/ui/TextField";
import { InstructionAudio } from "../../features/instructions/InstructionAudio";
import { LoadError, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, LocalMessage, translateFieldCodes } from "../../i18n/errors";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const FINAL: workersApi.IdentityStatus[] = ["demo_approved", "provider_verified", "manually_reviewed"];
const digitsOf = (value: string) => value.replace(/[\s-]/g, "");
const sameName = (a: string, b: string) => a.trim().replace(/\s+/g, " ").toLowerCase() === b.trim().replace(/\s+/g, " ").toLowerCase();

function StepStatus({ title, state }: { title: string; state: "done" | "pending" | "failed" }) {
  const { t } = useI18n();
  const icon =
    state === "done" ? (
      <CircleCheck className="size-5 text-success-strong" aria-hidden />
    ) : state === "failed" ? (
      <CircleX className="size-5 text-danger-strong" aria-hidden />
    ) : (
      <CircleDashed className="size-5 text-muted" aria-hidden />
    );
  return (
    <li className="flex items-center justify-between gap-2 rounded-xl border border-line px-3 py-2">
      <span className="flex items-center gap-2">
        {icon}
        {title}
      </span>
      <span className="text-sm font-bold">{t(`verify.steps.${state}`)}</span>
    </li>
  );
}

/** Editable review of the scan: the original OCR value stays visible, edits are marked as corrections. */
function ReviewForm({
  ocr,
  busy,
  fieldErrors,
  showDemoNote,
  onSubmit,
}: {
  ocr: workersApi.IdentityCase["ocr"];
  busy: string | null;
  fieldErrors: Record<string, string[]>;
  showDemoNote: boolean;
  onSubmit: (name: string, number: string) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(ocr.name ?? "");
  const [number, setNumber] = useState(ocr.cnic_number ?? "");
  const nameEdited = !sameName(name, ocr.name ?? "");
  const numberEdited = digitsOf(number) !== digitsOf(ocr.cnic_number ?? "");

  const scanNote = (value: string | null, edited: boolean) => (
    <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-muted">
      {value ? (
        <span className="flex flex-wrap items-center gap-1">
          {t("verify.fromScan")}
          <Ltr>{value}</Ltr>
        </span>
      ) : (
        <span>{t("verify.notInScan")}</span>
      )}
      {edited && <StatusBadge tone="info">{t("verify.edited")}</StatusBadge>}
    </p>
  );

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit(name, number);
  }

  return (
    <form onSubmit={handleSubmit} noValidate aria-labelledby="review-heading" className="space-y-4 rounded-2xl border border-line bg-white p-4">
      <h2 id="review-heading" className="text-lg font-bold">
        {t("verify.review.heading")}
      </h2>
      <div>
        <TextField label={t("verify.name.label")} value={name} onChange={setName} errors={fieldErrors.name} dir="ltr" lang="en" autoComplete="off" maxLength={80} />
        {scanNote(ocr.name, nameEdited)}
      </div>
      <div>
        <TextField
          label={t("verify.number.label")}
          hint={t("verify.number.hint")}
          value={number}
          onChange={setNumber}
          errors={fieldErrors.cnic_number}
          dir="ltr"
          inputMode="numeric"
          autoComplete="off"
          maxLength={20}
        />
        {scanNote(ocr.cnic_number, numberEdited)}
      </div>
      {showDemoNote && <p className="text-sm text-muted">{t("verify.why.demo")}</p>}
      <Button type="submit" fullWidth loading={busy === "submit"} loadingLabel={t("verify.submitting")} disabled={!name.trim() || !number.trim() || busy !== null} icon={<Send className="size-5" aria-hidden />}>
        {t("verify.submit")}
      </Button>
    </form>
  );
}

/**
 * Identity verification (M4): consent → photo of the card front → OCR on the server (Tesseract)
 * → the worker reviews/corrects the NAME and NUMBER → demo registry check (name and number must
 * match the same record). Scan, review and registry are reported separately; OCR never approves.
 */
export function VerifyIdentityPage() {
  const { t } = useI18n();
  const loaded = useLoad((signal) => workersApi.fetchIdentityCase(signal));
  const [current, setCurrent] = useState<workersApi.IdentityCase | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState<"start" | "scan" | "submit" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [fieldCodes, setFieldCodes] = useState<Record<string, string[]>>({});
  const [startingOver, setStartingOver] = useState(false);
  const captureInput = useRef<HTMLInputElement>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
  const fieldErrors = translateFieldCodes(fieldCodes, t);

  useEffect(() => {
    if (loaded.state.status === "ready") setCurrent(loaded.state.data.case);
  }, [loaded.state]);

  if (loaded.state.status === "loading") return <PageLoader />;
  if (loaded.state.status === "error") return <LoadError error={loaded.state.error} onRetry={loaded.retry} />;
  const provider = loaded.state.data.provider;

  async function run(step: NonNullable<typeof busy>, action: () => Promise<void>) {
    setFailure(null);
    setFieldCodes({});
    setBusy(step);
    try {
      await action();
    } catch (error) {
      // A failed scan still returns the attempt so the page can show the scan step as failed.
      if (error instanceof ApiError && error.details.case) setCurrent(error.details.case as workersApi.IdentityCase);
      setFieldCodes(fieldErrorCodes(error));
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  const start = () =>
    run("start", async () => {
      setCurrent((await workersApi.startIdentityCase()).case);
      setConsent(false);
      setStartingOver(false);
    });

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !current) return;
    if (file.size > MAX_IMAGE_BYTES) {
      setFailure(new LocalMessage("verify.photo.tooLarge"));
      return;
    }
    void run("scan", async () => setCurrent((await workersApi.scanCard(current.id, file, file.name)).case));
  }

  function submit(name: string, number: string) {
    if (!current) return;
    void run("submit", async () => setCurrent((await workersApi.submitDetails(current.id, name, number)).case));
  }

  const header = (
    <div className="space-y-3">
      <h1 className="text-3xl font-bold text-primary">{t("verify.title")}</h1>
      <InstructionAudio id="identity_consent" />
    </div>
  );
  const back = (
    <ButtonLink to={PATHS.worker} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
      {t("verify.backToDashboard")}
    </ButtonLink>
  );
  const setupMissing =
    failure instanceof ApiError && failure.code === "ai_provider_not_configured" && failure.details.capability === "cnic_ocr";
  const failureAlert =
    failure !== null && (setupMissing ? <Alert tone="danger">{t("verify.ocr.setup")}</Alert> : <Alert tone="danger">{describeError(failure, t)}</Alert>);

  // 1. Explain and ask for consent (no attempt yet, or starting over).
  if (!current || startingOver) {
    return (
      <div className="space-y-5">
        {header}
        <section aria-labelledby="why-heading" className="space-y-2 rounded-2xl border border-line bg-white p-4">
          <h2 id="why-heading" className="text-lg font-bold">
            {t("verify.why.heading")}
          </h2>
          <p>{t("verify.why.body")}</p>
        </section>
        {provider.simulated && <Alert tone="demo">{t("verify.why.demo")}</Alert>}
        {!provider.available && <Alert tone="warning">{t("worker.identity.unavailable")}</Alert>}
        {failureAlert}
        <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border-2 border-line bg-white p-3">
          <input type="checkbox" className="mt-1 size-6 shrink-0 accent-primary" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>{t("verify.consent")}</span>
        </label>
        <Button fullWidth disabled={!consent} loading={busy === "start"} loadingLabel={t("onboarding.saving")} icon={<ShieldCheck className="size-5" aria-hidden />} onClick={() => void start()}>
          {t("verify.start")}
        </Button>
        {back}
      </div>
    );
  }

  // Finished check.
  if (FINAL.includes(current.status)) {
    return (
      <div className="space-y-5">
        <h1 className="text-3xl font-bold text-primary">{t("verify.title")}</h1>
        <Alert
          tone={current.status === "demo_approved" ? "demo" : "success"}
          title={current.status === "demo_approved" ? undefined : t(`worker.identity.status.${current.status}`)}
        >
          {current.status === "demo_approved" && <p className="font-bold">{t("verify.result.passed")}</p>}
          {current.masked_cnic && (
            <p className="flex flex-wrap items-center gap-1.5">
              <span>{t("worker.identity.masked")}</span>
              <Ltr>{current.masked_cnic}</Ltr>
            </p>
          )}
          {current.registry.reference && (
            <p className="flex flex-wrap items-center gap-1.5">
              <span>{t("verify.reference")}</span>
              <Ltr>{current.registry.reference}</Ltr>
            </p>
          )}
        </Alert>
        {current.registry.demo_address && (
          <section aria-label={t("verify.demoAddress")} className="space-y-1 rounded-2xl border border-dashed border-warning/60 bg-warning-soft p-3">
            <p className="flex flex-wrap items-center gap-1.5">
              <StatusBadge tone="warning">{t("verify.demoAddress")}</StatusBadge>
              <span dir="ltr" lang="en">{current.registry.demo_address}</span>
            </p>
            <p className="text-sm text-muted">{t("verify.demoAddressNote")}</p>
          </section>
        )}
        {current.status === "demo_approved" && <p className="text-sm text-muted">{t("worker.identity.demoNote")}</p>}
        <p className="text-sm text-muted">{t("verify.privacy")}</p>
        {back}
      </div>
    );
  }

  const ocr = current.ocr;
  const scanned = ocr.status === "read" || ocr.status === "partial" || ocr.status === "unreadable";
  const scanState = ocr.status === "read" ? "done" : ocr.status === "not_run" ? "pending" : "failed";
  const registryState = current.registry.outcome === "match" ? "done" : current.registry.outcome === "not_checked" ? "pending" : "failed";

  // 2–4. Photo → OCR result → editable review → registry result.
  return (
    <div className="space-y-5">
      {header}
      <ol className="space-y-2" aria-label={t("verify.title")}>
        <StepStatus title={t("verify.steps.ocr")} state={scanState} />
        <StepStatus title={t("verify.steps.registry")} state={registryState} />
      </ol>

      {failureAlert}

      {current.status === "no_match" && (
        <Alert tone="warning" title={t("verify.result.notMatchedTitle")}>
          {current.registry.outcome === "name_mismatch" ? t("verify.result.nameMismatch") : t("verify.result.noRecord")}
        </Alert>
      )}

      <section aria-labelledby="photo-heading" className="space-y-3 rounded-2xl border border-line bg-white p-4">
        <h2 id="photo-heading" className="text-lg font-bold">
          {t("verify.photo.heading")}
        </h2>
        <p className="text-sm text-muted">{t("verify.photo.help")}</p>
        {busy === "scan" && <p role="status">{t("verify.photo.scanning")}</p>}
        {ocr.status === "read" && <Alert tone="success">{t("verify.ocr.read")}</Alert>}
        {ocr.status === "partial" && <Alert tone="warning">{t("verify.ocr.partial")}</Alert>}
        {ocr.status === "unreadable" && <Alert tone="warning">{t("verify.ocr.unreadable")}</Alert>}
        {ocr.status === "failed" && !failureAlert && ocr.failure?.startsWith("tesseract") && <Alert tone="danger">{t("verify.ocr.setup")}</Alert>}
        <input ref={captureInput} data-testid="capture-input" type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-hidden onChange={onFile} />
        <input ref={uploadInput} data-testid="upload-input" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" tabIndex={-1} aria-hidden onChange={onFile} />
        <div className="grid gap-2">
          <Button loading={busy === "scan"} loadingLabel={t("verify.photo.scanning")} disabled={busy !== null} icon={<Camera className="size-5" aria-hidden />} onClick={() => captureInput.current?.click()}>
            {scanned ? t("verify.photo.recapture") : t("verify.photo.capture")}
          </Button>
          <Button variant="secondary" disabled={busy !== null} icon={<Upload className="size-5" aria-hidden />} onClick={() => uploadInput.current?.click()}>
            {t("verify.photo.upload")}
          </Button>
        </div>
      </section>

      {scanned && (
        // Keyed by attempt and scan: every new scan starts the review from the ORIGINAL OCR values.
        <ReviewForm
          key={`${current.id}-${current.scan.count}`}
          ocr={ocr}
          busy={busy}
          fieldErrors={fieldErrors}
          showDemoNote={provider.simulated}
          onSubmit={submit}
        />
      )}

      <div className="grid gap-2">
        <Button
          variant="ghost"
          icon={<RotateCcw className="size-5" aria-hidden />}
          onClick={() => {
            setStartingOver(true);
            setFailure(null);
          }}
        >
          {t("verify.startOver")}
        </Button>
        {back}
      </div>
    </div>
  );
}
