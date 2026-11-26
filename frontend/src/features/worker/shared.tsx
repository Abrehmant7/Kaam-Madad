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

/** "Step 2 of 3" with a simple bar. Screen 1 is account creation. */
export function StepHeader({ step, title }: { step: 1 | 2 | 3; title: string }) {
  const { t } = useI18n();
  return (
    <div className="space-y-2">
      <p className="text-sm font-bold text-muted">{t("onboarding.step", { current: step, total: 3 })}</p>
      <div className="flex gap-1.5" aria-hidden>
        {[1, 2, 3].map((n) => (
          <span key={n} className={`h-2 flex-1 rounded-full ${n <= step ? "bg-primary" : "bg-line"}`} />
        ))}
      </div>
      <h1 className="text-3xl font-bold text-primary">{title}</h1>
    </div>
  );
}

export const label = (labels: catalogApi.Labels, language: Language) => labels[language] || labels.en;

export const onboardingPath = (step: workersApi.OnboardingStep) => (step === "work" ? "/worker/setup/work" : "/worker/setup/areas");
