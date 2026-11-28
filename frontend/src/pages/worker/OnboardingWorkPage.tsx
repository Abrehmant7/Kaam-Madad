import { ArrowRight, ChevronDown } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import * as catalogApi from "../../api/catalog";
import * as workersApi from "../../api/workers";
import { PATHS } from "../../auth/paths";
import { CatalogIcon } from "../../components/catalogIcons";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { IconTileGroup, type TileOption } from "../../components/ui/IconTile";
import { PageLoader } from "../../components/ui/PageLoader";
import { InstructionAudio } from "../../features/instructions/InstructionAudio";
import { VoiceAnswer, type VoiceSuggestion } from "../../features/voice/VoiceAnswer";
import { label, LoadError, StepHeader, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, translateFieldCodes } from "../../i18n/errors";

/**
 * Screen 2 — choose your work: trade, services offered, main speciality, and (under "More
 * options") services not offered. The server validates everything with the catalog rules.
 */
export function OnboardingWorkPage() {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const base = useLoad((signal) => Promise.all([workersApi.fetchWorker(signal), catalogApi.fetchTrades(signal)]));

  const [trade, setTrade] = useState<string[]>([]);
  const [offered, setOffered] = useState<string[]>([]);
  const [primary, setPrimary] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [questions, setQuestions] = useState<catalogApi.SpecialityQuestionSet | null>(null);
  const [initialised, setInitialised] = useState(false);
  const [errorCodes, setErrorCodes] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const errors = translateFieldCodes(errorCodes, t);

  // Start from what the worker saved before (resume or edit).
  useEffect(() => {
    if (base.state.status !== "ready" || initialised) return;
    const [dashboard, trades] = base.state.data;
    const saved = dashboard.profile;
    setTrade(saved.trade ? [saved.trade] : trades.results.length === 1 && trades.results[0] ? [trades.results[0].code] : []);
    setOffered(saved.services_offered);
    setPrimary(saved.primary_specialities);
    setExcluded(saved.services_not_offered);
    setInitialised(true);
  }, [base.state, initialised]);

  const selectedTrade = trade[0];
  useEffect(() => {
    if (!selectedTrade) return;
    const controller = new AbortController();
    setQuestions(null);
    catalogApi
      .fetchSpecialityQuestions(selectedTrade, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setQuestions(data);
        // Keep only services of this trade.
        const valid = new Set(data.choices.map((choice) => choice.code));
        setOffered((current) => current.filter((code) => valid.has(code)));
        setPrimary((current) => current.filter((code) => valid.has(code)));
        setExcluded((current) => current.filter((code) => valid.has(code)));
      })
      .catch((error: unknown) => !controller.signal.aborted && setFormError(error));
    return () => controller.abort();
  }, [selectedTrade]);

  /** Voice suggestions fill the same editable choices; the worker checks them and saves as usual. */
  function applyVoice({ fields }: VoiceSuggestion) {
    const nextOffered = fields.services_offered?.length ? fields.services_offered : offered;
    if (fields.trade) setTrade([fields.trade]);
    setOffered(nextOffered);
    // An unclear main speciality is left unselected (empty) for the worker to choose.
    setPrimary((fields.primary_specialities ?? []).filter((code) => nextOffered.includes(code)));
    if (fields.services_not_offered) setExcluded(fields.services_not_offered.filter((code) => !nextOffered.includes(code)));
  }

  function changeOffered(next: string[]) {
    setOffered(next);
    setPrimary((current) => current.filter((code) => next.includes(code)));
    setExcluded((current) => current.filter((code) => !next.includes(code)));
  }

  const serviceOptions = useMemo<TileOption<string>[]>(
    () =>
      (questions?.choices ?? []).map((choice) => ({
        value: choice.code,
        label: label(choice.labels, language),
        icon: <CatalogIcon id={choice.icon} className="size-8" />,
      })),
    [questions, language],
  );

  if (base.state.status === "loading") return <PageLoader />;
  if (base.state.status === "error") return <LoadError error={base.state.error} onRetry={base.retry} />;
  const [, trades] = base.state.data;

  const tradeOptions: TileOption<string>[] = trades.results.map((item) => ({
    value: item.code,
    label: label(item.labels, language),
    icon: <CatalogIcon id={item.icon} className="size-10" />,
  }));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setErrorCodes({});
    setSaving(true);
    try {
      const result = await workersApi.saveWork({
        trade: selectedTrade ?? "",
        services_offered: offered,
        primary_specialities: primary,
        services_not_offered: excluded,
      });
      navigate(result.onboarding.next_step === "areas" ? PATHS.workerAreas : PATHS.worker);
    } catch (error) {
      setErrorCodes(fieldErrorCodes(error));
      setFormError(error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} noValidate className="space-y-6">
      <StepHeader step={2} flow="worker" title={t("onboarding.work.title")} />
      <InstructionAudio id="onboarding_work" />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      {/* Beside the manual choices on desktop; above them on phones. */}
      <div className="lg:sticky lg:top-24 lg:order-last">
        <VoiceAnswer kind="onboarding_work" onSuggest={applyVoice} />
      </div>
      <div className="card min-w-0 space-y-6 p-4 sm:p-5">
      {formError !== null && <Alert tone="danger">{describeError(formError, t)}</Alert>}

      <IconTileGroup label={t("onboarding.work.tradeLabel")} mode="single" options={tradeOptions} value={trade} onChange={setTrade} errors={errors.trade} />

      {selectedTrade && !questions && <PageLoader />}
      {questions && (
        <>
          <div className="space-y-1">
            <IconTileGroup
              label={t("onboarding.work.servicesLabel")}
              mode="multiple"
              options={serviceOptions}
              value={offered}
              onChange={changeOffered}
              errors={errors.services_offered}
            />
            <p className="text-sm text-muted">{t("onboarding.work.servicesHelp")}</p>
          </div>

          <div className="space-y-1">
            {offered.length === 0 ? (
              <fieldset>
                <legend className="mb-2 font-bold">{t("onboarding.work.mainLabel")}</legend>
                <p className="rounded-xl border border-dashed border-line p-3 text-muted">{t("onboarding.work.mainEmpty")}</p>
              </fieldset>
            ) : (
              <IconTileGroup
                label={t("onboarding.work.mainLabel")}
                mode="single"
                options={serviceOptions.filter((option) => offered.includes(option.value))}
                value={primary}
                onChange={setPrimary}
                errors={errors.primary_specialities}
              />
            )}
            <p className="text-sm text-muted">{t("onboarding.work.mainHelp")}</p>
          </div>

          <details className="group rounded-2xl border border-line bg-white p-3" open={excluded.length > 0 || Boolean(errors.services_not_offered)}>
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 font-bold text-primary">
              {t("onboarding.work.moreOptions")}
              <ChevronDown className="size-5 transition-transform group-open:rotate-180" aria-hidden />
            </summary>
            <div className="mt-3 space-y-1">
              <IconTileGroup
                label={t("onboarding.work.excludedLabel")}
                mode="multiple"
                options={serviceOptions.filter((option) => !offered.includes(option.value))}
                value={excluded}
                onChange={setExcluded}
                errors={errors.services_not_offered}
              />
              <p className="text-sm text-muted">{t("onboarding.work.excludedHelp")}</p>
            </div>
          </details>
        </>
      )}

      <Button
        type="submit"
        fullWidth
        loading={saving}
        loadingLabel={t("onboarding.saving")}
        icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />}
      >
        {t("onboarding.work.save")}
      </Button>
      </div>
      </div>
    </form>
  );
}
