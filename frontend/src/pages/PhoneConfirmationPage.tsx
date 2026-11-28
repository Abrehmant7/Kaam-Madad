import { CircleCheck, House, MessageSquare, RefreshCw } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import * as authApi from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/context";
import { homePathFor } from "../auth/paths";
import { Ltr } from "../components/Ltr";
import { Alert } from "../components/ui/Alert";
import { Button, ButtonLink } from "../components/ui/Button";
import { PageLoader } from "../components/ui/PageLoader";
import { TextField } from "../components/ui/TextField";
import { PhoneConfirmationBadge } from "../features/phone/PhoneConfirmationStatus";
import { formatMinutesSeconds, useCountdown } from "../hooks/useCountdown";
import { useI18n } from "../i18n/context";
import { describeError, fieldErrorCodes, fieldErrorText, LocalMessage } from "../i18n/errors";

type Load = { status: "loading" } | { status: "error"; error: unknown } | { status: "ready"; data: authApi.PhoneConfirmationState };

export function PhoneConfirmationPage() {
  const { t } = useI18n();
  const { user, setUser } = useAuth();
  const [params] = useSearchParams();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [demoCode, setDemoCode] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [codeErrorCodes, setCodeErrors] = useState<string[]>([]);
  const codeErrors = codeErrorCodes.map((errorCode) => fieldErrorText(errorCode, t));
  const [message, setMessage] = useState<{ tone: "danger" | "success"; content: unknown } | null>(null);
  const [busy, setBusy] = useState<"send" | "verify" | null>(null);

  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoad({ status: "loading" });
    try {
      const data = await authApi.fetchPhoneConfirmation(signal);
      if (!signal?.aborted) setLoad({ status: "ready", data });
    } catch (error) {
      if (!signal?.aborted) setLoad({ status: "error", error });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [reload]);

  const data = load.status === "ready" ? load.data : null;
  const active = data?.active_code ?? null;
  const expiresIn = useCountdown(active?.expires_in_seconds ?? null, active?.id);
  const resendIn = useCountdown(active?.resend_available_in_seconds ?? null, active?.id);

  async function sendCode() {
    setBusy("send");
    setMessage(null);
    setCodeErrors([]);
    try {
      const result = await authApi.startPhoneConfirmation();
      setDemoCode(result.demo?.code ?? null);
      setCode("");
      setLoad({ status: "ready", data: result });
    } catch (error) {
      setMessage({ tone: "danger", content: error });
    } finally {
      setBusy(null);
    }
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    if (!code.trim()) {
      setCodeErrors(["required"]);
      return;
    }
    setBusy("verify");
    try {
      const session = await authApi.verifyPhoneCode(code);
      if (session.user) setUser(session.user);
      setDemoCode(null);
      setMessage({ tone: "success", content: new LocalMessage("phone.confirmedSuccess") });
      await reload();
    } catch (error) {
      setCodeErrors(fieldErrorCodes(error).code ?? []);
      setMessage({ tone: "danger", content: error });
      // Attempts/expiry changed on the server: refresh the displayed state.
      if (error instanceof ApiError && error.code !== "validation_error") {
        const fresh = await authApi.fetchPhoneConfirmation().catch(() => null);
        if (fresh) setLoad({ status: "ready", data: fresh });
      }
    } finally {
      setBusy(null);
    }
  }

  if (load.status === "loading" && !data) return <PageLoader />;

  const confirmed = data?.status === "confirmed";
  const provider = data?.provider;
  const home = user ? homePathFor(user) : "/";

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("phone.title")}</h1>

      {params.get("welcome") === "1" && <Alert tone="success">{t("signup.success")}</Alert>}

      {load.status === "error" && (
        <Alert tone="danger" title={describeError(load.error, t)}>
          <Button variant="ghost" className="min-h-11 px-0" icon={<RefreshCw className="size-4" aria-hidden />} onClick={() => void reload()}>
            {t("common.retry")}
          </Button>
        </Alert>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <PhoneConfirmationBadge confirmation={data} />
            {user && <Ltr className="text-sm text-muted">{user.phone_number_masked}</Ltr>}
          </div>
          <p className="text-sm text-muted">{t("phone.boundary")}</p>

          {message && <Alert tone={message.tone}>{describeError(message.content, t)}</Alert>}

          {!confirmed && provider && !provider.available && <Alert tone="info">{t("phone.unavailable")}</Alert>}

          {!confirmed && provider?.available && (
            <section className="space-y-4 card p-4">
              {provider.simulated && <Alert tone="demo">{t("phone.demoExplainer")}</Alert>}

              {demoCode && (
                <div className="rounded-xl border-2 border-dashed border-accent bg-accent-soft p-3 text-center" aria-live="polite">
                  <p className="text-sm font-bold text-warning-strong">{t("phone.demoCodeLabel")}</p>
                  <Ltr className="text-3xl font-bold tracking-[0.3em]">{demoCode}</Ltr>
                </div>
              )}
              {active && !demoCode && provider.simulated && <p className="text-sm text-muted">{t("phone.codeHiddenAfterReload")}</p>}

              {active && (
                <form onSubmit={(event) => void verify(event)} noValidate className="space-y-3">
                  <TextField
                    label={t("phone.codeLabel")}
                    value={code}
                    onChange={(value) => {
                      setCode(value);
                      setCodeErrors([]);
                    }}
                    errors={codeErrors}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    dir="ltr"
                    maxLength={12}
                  />
                  <p className="flex flex-wrap gap-x-4 text-sm text-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <span>{t("phone.expiresIn")}</span>
                      <Ltr>{formatMinutesSeconds(expiresIn)}</Ltr>
                    </span>
                    <span>{t("phone.attemptsRemaining", { count: active.attempts_remaining })}</span>
                  </p>
                  <Button
                    type="submit"
                    fullWidth
                    loading={busy === "verify"}
                    loadingLabel={t("phone.verifying")}
                    icon={<CircleCheck className="size-5" aria-hidden />}
                  >
                    {t("phone.verify")}
                  </Button>
                </form>
              )}

              <Button
                variant={active ? "secondary" : "primary"}
                fullWidth
                disabled={Boolean(active) && resendIn > 0}
                loading={busy === "send"}
                loadingLabel={t("phone.sending")}
                icon={<MessageSquare className="size-5" aria-hidden />}
                onClick={() => void sendCode()}
              >
                {active
                  ? resendIn > 0
                    ? t("phone.resendIn", { seconds: resendIn })
                    : t("phone.resend")
                  : provider.simulated
                    ? t("phone.sendDemoCode")
                    : t("phone.sendCode")}
              </Button>
            </section>
          )}

          <ButtonLink to={home} variant={confirmed ? "primary" : "ghost"} icon={<House className="size-5" aria-hidden />} fullWidth>
            {confirmed ? t("phone.continueHome") : t("phone.skip")}
          </ButtonLink>
        </>
      )}
    </div>
  );
}
