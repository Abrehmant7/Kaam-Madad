import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import * as catalogApi from "../../api/catalog";
import * as workersApi from "../../api/workers";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import type { Language } from "../../i18n/types";

export type Load<T> = { status: "loading" } | { status: "error"; error: unknown } | { status: "ready"; data: T };

/** Load something once (and again on retry). Aborts when the component unmounts. */
export function useLoad<T>(loader: (signal: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<Load<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    loader(controller.signal)
      .then((data) => !controller.signal.aborted && setState({ status: "ready", data }))
      .catch((error: unknown) => !controller.signal.aborted && setState({ status: "error", error }));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, ...deps]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const set = useCallback((data: T) => setState({ status: "ready", data }), []);
  return { state, retry, set };
}

export function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <Alert tone="danger">{describeError(error, t)}</Alert>
      <Button icon={<RefreshCw className="size-5" aria-hidden />} onClick={onRetry}>
        {t("common.retry")}
      </Button>
    </div>
  );
}

const FLOW_LABELS = {
  worker: ["onboarding.flow.account", "onboarding.flow.work", "onboarding.flow.areas"],
  request: ["jobs.flow.describe", "jobs.flow.details", "jobs.flow.review"],
} as const;

/** "Step 2 of 3" with named steps (worker signup or customer request). Screen 1 of signup is account creation. */
export function StepHeader({ step, title, flow }: { step: 1 | 2 | 3; title: string; flow?: keyof typeof FLOW_LABELS }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <p className="text-sm font-bold text-muted">{t("onboarding.step", { current: step, total: 3 })}</p>
      <ol className="grid grid-cols-3 gap-2" aria-hidden={flow ? undefined : true}>
        {[1, 2, 3].map((n) => (
          <li key={n} aria-current={n === step ? "step" : undefined}
            className={`border-t-4 pt-1.5 text-xs leading-tight sm:text-sm ${
              n === step ? "border-primary font-bold text-primary" : n < step ? "border-primary/40 text-muted" : "border-line text-muted"
            }`}>
            {flow && FLOW_LABELS[flow][n - 1] && (
              <>
                <span className="me-1 inline-grid size-5 place-items-center rounded-full bg-primary-soft font-sans text-[11px] font-bold text-primary">{n}</span>
                {t(FLOW_LABELS[flow][n - 1] ?? "onboarding.flow.account")}
              </>
            )}
          </li>
        ))}
      </ol>
      <h1 className="text-2xl font-bold text-ink sm:text-3xl">{title}</h1>
    </div>
  );
}

export const label = (labels: catalogApi.Labels, language: Language) => labels[language] || labels.en;

export const onboardingPath = (step: workersApi.OnboardingStep) => (step === "work" ? "/worker/setup/work" : "/worker/setup/areas");
