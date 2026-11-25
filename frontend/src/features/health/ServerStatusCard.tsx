import type { ReactNode } from "react";

import { CheckCircleIcon, NoConnectionIcon, RefreshIcon, SpinnerIcon, WarningIcon } from "../../components/icons";
import { Ltr } from "../../components/Ltr";
import { useI18n } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/types";
import { type ServerStatus, useServerStatus } from "./useServerStatus";

interface Presentation {
  icon: ReactNode;
  messageKey: TranslationKey;
  tone: "neutral" | "success" | "warning" | "danger";
  requestId: string | null;
}

function present(status: ServerStatus): Presentation {
  switch (status.kind) {
    case "checking":
      return { icon: <SpinnerIcon />, messageKey: "status.checking", tone: "neutral", requestId: null };
    case "ready":
      return { icon: <CheckCircleIcon />, messageKey: "status.ready", tone: "success", requestId: null };
    case "not_ready":
      return { icon: <WarningIcon />, messageKey: "status.notReady", tone: "warning", requestId: status.requestId };
    case "connection_error": {
      const messageKey: TranslationKey =
        status.reason === "offline" ? "status.offline" : status.reason === "timeout" ? "status.timeout" : "status.unreachable";
      return { icon: <NoConnectionIcon />, messageKey, tone: "danger", requestId: null };
    }
    case "unexpected":
      return { icon: <WarningIcon />, messageKey: "status.unexpected", tone: "danger", requestId: status.requestId };
  }
}

const TONE_CLASSES: Record<Presentation["tone"], string> = {
  neutral: "border-line bg-white text-ink",
  success: "border-success/40 bg-success-soft text-success-strong",
  warning: "border-warning/50 bg-warning-soft text-warning-strong",
  danger: "border-danger/40 bg-danger-soft text-danger-strong",
};

export function ServerStatusCard() {
  const { t } = useI18n();
  const { status, retry } = useServerStatus();
  const { icon, messageKey, tone, requestId } = present(status);
  const canRetry = status.kind !== "checking" && status.kind !== "ready";

  return (
    <section aria-labelledby="server-status-heading" className="rounded-2xl border border-line bg-white p-4 shadow-sm">
      <h2 id="server-status-heading" className="mb-3 text-lg font-bold">
        {t("status.heading")}
      </h2>

      <div
        role="status"
        aria-live="polite"
        aria-busy={status.kind === "checking"}
        className={`flex items-start gap-3 rounded-xl border p-3 ${TONE_CLASSES[tone]}`}
      >
        <span className="mt-1 shrink-0">{icon}</span>
        <p>{t(messageKey)}</p>
      </div>

      {requestId && (
        <p className="mt-2 text-sm text-muted">
          {t("status.reference")}: <Ltr className="text-xs">{requestId}</Ltr>
        </p>
      )}

      {canRetry && (
        <button type="button" onClick={retry} className="btn-primary mt-4 w-full">
          <RefreshIcon className="size-5" />
          <span>{t("status.retry")}</span>
        </button>
      )}
    </section>
  );
}
