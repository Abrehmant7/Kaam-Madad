import { ArrowLeft, CircleCheck, IdCard, ImagePlus, ShieldCheck, UserRound } from "lucide-react";
import { type ChangeEvent, type ReactNode, useEffect, useRef, useState } from "react";

import * as workersApi from "../../api/workers";
import { PATHS } from "../../auth/paths";
import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { LoadError, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, LocalMessage } from "../../i18n/errors";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const FINAL: workersApi.IdentityStatus[] = ["demo_approved", "provider_verified", "manually_reviewed"];
/** Fictional samples shipped with the app (frontend/public/demo-samples). */
export const SAMPLES = { cnic: "/demo-samples/sample-cnic.png", selfie: "/demo-samples/sample-selfie.png" } as const;
type Slot = keyof typeof SAMPLES;
interface Picked {
  blob: Blob;
  name: string;
  url: string;
}

function UploadSlot({ slot, title, icon, picked, onPick, disabled }: {
  slot: Slot;
  title: string;
  icon: ReactNode;
  picked: Picked | null;
  onPick: (slot: Slot, picked: Picked | null, error?: LocalMessage) => void;
  disabled: boolean;
}) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);

  async function pickSample() {
    setLoading(true);
    try {
      const response = await fetch(SAMPLES[slot]);
      if (!response.ok) throw new Error(String(response.status));
      const blob = await response.blob();
      onPick(slot, { blob, name: `sample-${slot}.png`, url: URL.createObjectURL(blob) });
    } catch {
      onPick(slot, null, new LocalMessage("demoVerify.sampleFailed"));
    } finally {
      setLoading(false);
    }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      onPick(slot, null, new LocalMessage("verify.photo.tooLarge"));
      return;
    }
    onPick(slot, { blob: file, name: file.name || slot, url: URL.createObjectURL(file) });
  }

  return (
    <section aria-label={title} className="space-y-3 card p-4">
      <h2 className="flex items-center gap-2 text-lg font-bold">
        {icon}
        {title}
        {picked && <StatusBadge tone="success">{t("demoVerify.chosen")}</StatusBadge>}
      </h2>
      {picked && <img src={picked.url} alt={title} className="max-h-40 rounded-xl border border-line object-contain" />}
      <input ref={input} data-testid={`${slot}-input`} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" tabIndex={-1} aria-hidden onChange={onFile} />
      <div className="grid gap-2 sm:grid-cols-2">
        <Button variant={picked ? "secondary" : "primary"} disabled={disabled} loading={loading} icon={icon} onClick={() => void pickSample()}>
          {t("demoVerify.useSample")}
        </Button>
        <Button variant="secondary" disabled={disabled} icon={<ImagePlus className="size-5" aria-hidden />} onClick={() => input.current?.click()}>
          {t("demoVerify.upload")}
        </Button>
      </div>
    </section>
  );
}

/**
 * Event demo verification: a sample CNIC and a sample selfie. The server checks both only as images (type, size,
 * dimensions) and records the existing "demo approved" status — no OCR, face matching or registry, nothing stored,
 * nothing sent to a provider. Demo deployments only; it is not NADRA verification. The dashboard works without it.
 */
export function DemoVerifyPage() {
  const { t } = useI18n();
  const { config } = useAuth();
  const loaded = useLoad((signal) => workersApi.fetchIdentityCase(signal));
  const [current, setCurrent] = useState<workersApi.IdentityCase | null>(null);
  const [picked, setPicked] = useState<Record<Slot, Picked | null>>({ cnic: null, selfie: null });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  useEffect(() => {
    if (loaded.state.status === "ready") setCurrent(loaded.state.data.case);
  }, [loaded.state]);
  useEffect(() => () => Object.values(picked).forEach((item) => item && URL.revokeObjectURL(item.url)), [picked]);

  if (loaded.state.status === "loading") return <PageLoader />;
  if (loaded.state.status === "error") return <LoadError error={loaded.state.error} onRetry={loaded.retry} />;

  const back = (label: string) => (
    <ButtonLink to={PATHS.worker} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
      {label}
    </ButtonLink>
  );
  const header = (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("demoVerify.title")}</h1>
      <StatusBadge tone="warning">{t("demoVerify.sampleOnly")}</StatusBadge>
    </div>
  );

  if (current && FINAL.includes(current.status)) {
    return (
      <div className="space-y-5">
        {header}
        <Alert tone={current.status === "demo_approved" ? "demo" : "success"}>
          <p className="flex items-center gap-2 font-bold">
            <CircleCheck className="size-5" aria-hidden />
            {current.status === "demo_approved" ? t("demoVerify.complete") : t(`worker.identity.status.${current.status}`)}
          </p>
          {current.status === "demo_approved" && <p>{t("demoVerify.completeNote")}</p>}
        </Alert>
        <p className="text-sm text-muted">{t("demoVerify.notNadra")}</p>
        {back(t("verify.backToDashboard"))}
      </div>
    );
  }

  if (config && config.deployment_mode !== "demo") {
    return (
      <div className="space-y-5">
        {header}
        <Alert tone="warning">{t("demoVerify.unavailable")}</Alert>
        {back(t("verify.backToDashboard"))}
      </div>
    );
  }

  function pick(slot: Slot, next: Picked | null, error?: LocalMessage) {
    setFailure(error ?? null);
    if (next || !error) setPicked((currentPicked) => ({ ...currentPicked, [slot]: next }));
  }

  async function submit() {
    const { cnic, selfie } = picked;
    if (!cnic || !selfie) return;
    setFailure(null);
    setBusy(true);
    try {
      setCurrent((await workersApi.demoVerify(cnic.blob, cnic.name, selfie.blob, selfie.name)).case);
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {header}
      <Alert tone="demo" title={t("demoVerify.sampleOnly")}>
        <p>{t("demoVerify.explain")}</p>
        <p className="font-bold">{t("demoVerify.notNadra")}</p>
      </Alert>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      <div className="grid items-start gap-4 md:grid-cols-2">
        <UploadSlot slot="cnic" title={t("demoVerify.cnic")} icon={<IdCard className="size-5" aria-hidden />} picked={picked.cnic} onPick={pick} disabled={busy} />
        <UploadSlot slot="selfie" title={t("demoVerify.selfie")} icon={<UserRound className="size-5" aria-hidden />} picked={picked.selfie} onPick={pick} disabled={busy} />
      </div>
      <Button className="w-full sm:w-auto sm:min-w-64" disabled={!picked.cnic || !picked.selfie || busy} loading={busy} loadingLabel={t("demoVerify.submitting")}
        icon={<ShieldCheck className="size-5" aria-hidden />} onClick={() => void submit()}>
        {t("demoVerify.submit")}
      </Button>
      {back(t("demoVerify.later"))}
    </div>
  );
}
