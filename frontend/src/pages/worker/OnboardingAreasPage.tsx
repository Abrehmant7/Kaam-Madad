import { ArrowLeft, Building2, MapPin, Save, Volume2 } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router";

import * as workersApi from "../../api/workers";
import { PATHS } from "../../auth/paths";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { IconTileGroup, type TileOption } from "../../components/ui/IconTile";
import { PageLoader } from "../../components/ui/PageLoader";
import { InstructionAudio } from "../../features/instructions/InstructionAudio";
import { citiesOf, type JobCatalog, labeller, loadJobCatalog } from "../../features/jobs/catalog";
import { ReadAloud } from "../../features/voice/ReadAloud";
import { VoiceAnswer, type VoiceSuggestion } from "../../features/voice/VoiceAnswer";
import { label, LoadError, StepHeader, useLoad } from "../../features/worker/shared";
import type { I18nContextValue } from "../../i18n/context";
import { useI18n } from "../../i18n/context";
import type { Language } from "../../i18n/types";
import { describeError, fieldErrorCodes, translateFieldCodes } from "../../i18n/errors";

/**
 * Text for "Listen to my choices": built ONLY from the worker's actual selections and localized catalog labels
 * (trade, services, main speciality, work not done, areas). No phone number, password, code or identity data.
 */
export function choicesSpeech(
  profile: workersApi.WorkerProfileData,
  city: string | null,
  areas: string[],
  catalog: JobCatalog,
  language: Language,
  t: I18nContextValue["t"],
): string {
  const name = labeller(catalog, language);
  const join = (codes: string[]) => codes.map(name.service).join(language === "ur" ? "، " : ", ");
  const parts = [t("onboarding.listen.trade", { trade: name.trade(profile.trade) })];
  if (profile.services_offered.length) parts.push(t("onboarding.listen.services", { services: join(profile.services_offered) }));
  if (profile.primary_specialities.length) parts.push(t("onboarding.listen.main", { services: join(profile.primary_specialities) }));
  if (profile.services_not_offered.length) parts.push(t("onboarding.listen.notOffered", { services: join(profile.services_not_offered) }));
  parts.push(
    city && areas.length
      ? t("onboarding.listen.areas", { areas: areas.map(name.area).join(language === "ur" ? "، " : ", "), city: name.city(city) })
      : t("onboarding.listen.noAreas"),
  );
  return parts.join(" ");
}

/**
 * Screen 3 — choose where you work: a city and the catalog areas the worker will travel to.
 * No browser location or GPS is requested. Optional voice answer; "Listen to my choices" reads the selections.
 */
export function OnboardingAreasPage() {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const base = useLoad((signal) => Promise.all([workersApi.fetchWorker(signal), loadJobCatalog(signal)]));
  const [city, setCity] = useState<string[]>([]);
  const [areas, setAreas] = useState<string[]>([]);
  const [initialised, setInitialised] = useState(false);
  const [errorCodes, setErrorCodes] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const errors = translateFieldCodes(errorCodes, t);

  useEffect(() => {
    if (base.state.status !== "ready" || initialised) return;
    const saved = base.state.data[0].profile;
    setCity(saved.city ? [saved.city] : []);
    setAreas(saved.service_areas);
    setInitialised(true);
  }, [base.state, initialised]);

  const catalog = base.state.status === "ready" ? base.state.data[1] : null;
  const allAreas = useMemo(() => catalog?.areas ?? [], [catalog]);
  const cities = useMemo(() => (catalog ? citiesOf(catalog) : []), [catalog]);

  if (base.state.status === "loading") return <PageLoader />;
  if (base.state.status === "error") return <LoadError error={base.state.error} onRetry={base.retry} />;
  const [dashboard, jobCatalog] = base.state.data;
  // Screens are completed in order: resume at the work step if it is not done.
  if (!dashboard.onboarding.steps.work.complete) return <Navigate to={PATHS.workerWork} replace />;

  const selectedCity = city[0];
  const cityOptions: TileOption<string>[] = cities.map((item) => ({
    value: item.code,
    label: label(item.labels, language),
    icon: <Building2 className="size-8" aria-hidden />,
  }));
  const areaOptions: TileOption<string>[] = allAreas
    .filter((area) => area.city.code === selectedCity)
    .map((area) => ({ value: area.code, label: label(area.labels, language), icon: <MapPin className="size-7" aria-hidden /> }));

  function changeCity(next: string[]) {
    setCity(next);
    const inCity = new Set(allAreas.filter((area) => area.city.code === next[0]).map((area) => area.code));
    setAreas((current) => current.filter((code) => inCity.has(code)));
  }

  function applyVoice({ fields }: VoiceSuggestion) {
    const nextCity = fields.city ?? selectedCity;
    if (!nextCity) return;
    const inCity = new Set(allAreas.filter((area) => area.city.code === nextCity).map((area) => area.code));
    setCity([nextCity]);
    setAreas((fields.service_areas ?? []).filter((code) => inCity.has(code)));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setErrorCodes({});
    setSaving(true);
    try {
      const result = await workersApi.saveAreas({ city: selectedCity ?? "", service_areas: areas });
      if (result.onboarding.next_step === "work") navigate(PATHS.workerWork);
      // Signup done: offer the (demo) verification next. The dashboard stays usable without it.
      else navigate(result.identity.counts_here ? PATHS.worker : PATHS.workerVerify);
    } catch (error) {
      setErrorCodes(fieldErrorCodes(error));
      setFormError(error);
    } finally {
      setSaving(false);
    }
  }

  const areaName = labeller(jobCatalog, language).area;

  return (
    <form onSubmit={(event) => void handleSubmit(event)} noValidate className="space-y-6">
      <StepHeader step={3} flow="worker" title={t("onboarding.areas.title")} />
      <InstructionAudio id="onboarding_areas" />
      <p className="text-muted">{t("onboarding.areas.explain")}</p>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      {/* Beside the manual choices on desktop; above them on phones. */}
      <div className="lg:sticky lg:top-24 lg:order-last">
        <VoiceAnswer kind="onboarding_areas" onSuggest={applyVoice} describe={areaName} />
      </div>
      <div className="card min-w-0 space-y-6 p-4 sm:p-5">
      {formError !== null && <Alert tone="danger">{describeError(formError, t)}</Alert>}

      <IconTileGroup label={t("onboarding.areas.cityLabel")} mode="single" options={cityOptions} value={city} onChange={changeCity} errors={errors.city} />

      {selectedCity ? (
        <IconTileGroup
          label={t("onboarding.areas.areasLabel")}
          mode="multiple"
          options={areaOptions}
          value={areas}
          onChange={setAreas}
          errors={errors.service_areas}
        />
      ) : (
        <fieldset>
          <legend className="mb-2 font-bold">{t("onboarding.areas.areasLabel")}</legend>
          <p className="rounded-xl border border-dashed border-line p-3 text-muted">{t("onboarding.areas.chooseCityFirst")}</p>
        </fieldset>
      )}

      <section aria-labelledby="listen-heading" className="space-y-2 rounded-xl bg-primary-soft/60 p-3">
        <h2 id="listen-heading" className="flex items-center gap-2 font-bold text-primary">
          <Volume2 className="size-5" aria-hidden />
          {t("onboarding.listen.heading")}
        </h2>
        <p className="text-sm text-muted">{t("onboarding.listen.note")}</p>
        <ReadAloud text={choicesSpeech(dashboard.profile, selectedCity ?? null, areas, jobCatalog, language, t)} language={language} />
      </section>

      <div className="grid gap-3">
        <Button type="submit" fullWidth loading={saving} loadingLabel={t("onboarding.saving")} icon={<Save className="size-5" aria-hidden />}>
          {t("onboarding.areas.save")}
        </Button>
        <ButtonLink to={PATHS.workerWork} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
          {t("common.back")}
        </ButtonLink>
      </div>
      </div>
      </div>
    </form>
  );
}
