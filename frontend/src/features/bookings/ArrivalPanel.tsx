import { KeyRound, MapPinCheck, Play, ShieldAlert } from "lucide-react";
import { useState } from "react";

import * as bookingsApi from "../../api/bookings";
import { ApiError } from "../../api/client";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, fieldErrorText } from "../../i18n/errors";
import { formatTime } from "../jobs/time";

type Act = (action: () => Promise<bookingsApi.Booking>, options?: { showError?: boolean }) => Promise<boolean>;

/** Arrival (worker), the one-time code (customer) and start with the code (worker) — BK-04, BK-05. */
export function ArrivalPanel({ booking, act, busy }: { booking: bookingsApi.Booking; act: Act; busy: boolean }) {
  const { t, language } = useI18n();
  const [shown, setShown] = useState<{ value: string; expires_at: string } | null>(null);
  const [code, setCode] = useState("");
  const [codeFailure, setCodeFailure] = useState<unknown>(null);
  const state = booking.arrival_code;

  if (booking.status === "confirmed") {
    if (booking.role === "worker") {
      return (
        <section className="space-y-2 card p-4">
          <h2 className="text-lg font-bold">{t("arrival.workerTitle")}</h2>
          <p className="text-sm">{t("arrival.workerIntro")}</p>
          <Button fullWidth loading={busy} loadingLabel={t("onboarding.saving")} icon={<MapPinCheck className="size-5" aria-hidden />}
            onClick={() => void act(() => bookingsApi.markArrived(booking.id))}>
            {t("arrival.markArrived")}
          </Button>
        </section>
      );
    }
    return <Alert tone="info">{t("arrival.customerWaiting")}</Alert>;
  }
  if (booking.status !== "arrived") return null;

  if (booking.role === "customer") {
    async function reveal() {
      setShown(null);
      await act(async () => {
        const result = await bookingsApi.issueArrivalCode(booking.id);
        if (result.code) setShown(result.code); // shown once; never stored on this device
        return result;
      });
    }
    return (
      <section aria-labelledby="code-heading" className="space-y-3 card-action p-4">
        <h2 id="code-heading" className="flex items-center gap-2 text-lg font-bold">
          <KeyRound className="size-5" aria-hidden />
          {t("arrival.codeTitle")}
        </h2>
        <p>{t("arrival.customerArrived")}</p>
        <Alert tone="warning" title={t("arrival.checkTitle")}>
          <p>{t("arrival.checkBody")}</p>
          <p className="mt-1 text-sm">{t("arrival.limits")}</p>
        </Alert>
        {shown ? (
          <div className="space-y-2 rounded-xl bg-surface p-4 text-center">
            <p className="text-sm text-muted">{t("arrival.readToWorker")}</p>
            <p dir="ltr" className="font-mono text-4xl font-bold tracking-[0.4em]" aria-live="polite">{shown.value}</p>
            <p className="text-sm">{t("arrival.validUntil")} <bdi dir="ltr">{formatTime(shown.expires_at, language)}</bdi></p>
            <p className="text-xs text-muted">{t("arrival.shownOnce")}</p>
          </div>
        ) : state?.active ? (
          <p className="text-sm">{t("arrival.activeElsewhere")}</p>
        ) : null}
        <Button fullWidth variant={shown ? "secondary" : "primary"} loading={busy} loadingLabel={t("onboarding.saving")}
          icon={<KeyRound className="size-5" aria-hidden />} onClick={() => void reveal()}>
          {shown || state?.active ? t("arrival.newCode") : t("arrival.showCode")}
        </Button>
      </section>
    );
  }

  // Worker: enter the code the customer reads out.
  async function start() {
    setCodeFailure(null);
    await act(async () => {
      try {
        return await bookingsApi.startWithCode(booking.id, code.replace(/\s/g, ""));
      } catch (error) {
        setCodeFailure(error);
        throw error;
      }
    }, { showError: false });
  }
  const left = codeFailure instanceof ApiError && typeof codeFailure.details.attempts_remaining === "number"
    ? codeFailure.details.attempts_remaining : state?.attempts_remaining;
  const fieldErrors = fieldErrorCodes(codeFailure).code ?? [];
  return (
    <section aria-labelledby="start-heading" className="space-y-3 card-action p-4">
      <h2 id="start-heading" className="text-lg font-bold">{t("arrival.startTitle")}</h2>
      <p>{t("arrival.startIntro")}</p>
      {!state?.active && (
        <Alert tone="info">{state?.locked ? t("arrival.lockedWorker") : state?.expired ? t("arrival.expiredWorker") : t("arrival.noCodeYet")}</Alert>
      )}
      <TextField label={t("arrival.codeLabel")} value={code} onChange={(value) => setCode(value.replace(/[^\d ]/g, ""))} inputMode="numeric"
        autoComplete="one-time-code" maxLength={7} dir="ltr" errors={fieldErrors.map((c) => fieldErrorText(c, t))}
        hint={left !== undefined ? t("arrival.attemptsLeft", { count: left }) : undefined} />
      {codeFailure !== null && fieldErrors.length === 0 && (
        <Alert tone="danger" title={t("arrival.notAccepted")}>
          <span className="flex items-center gap-2"><ShieldAlert className="size-4" aria-hidden />{describeError(codeFailure, t)}</span>
        </Alert>
      )}
      <Button fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={code.replace(/\s/g, "").length !== 6}
        icon={<Play className="size-5" aria-hidden />} onClick={() => void start()}>
        {t("arrival.start")}
      </Button>
    </section>
  );
}
