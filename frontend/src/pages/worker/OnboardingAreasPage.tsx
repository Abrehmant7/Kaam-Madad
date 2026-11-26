import { ArrowLeft, Building2, MapPin, Save } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router";

import * as catalogApi from "../../api/catalog";
import * as workersApi from "../../api/workers";
import { PATHS } from "../../auth/paths";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { IconTileGroup, type TileOption } from "../../components/ui/IconTile";
import { PageLoader } from "../../components/ui/PageLoader";
import { InstructionAudio } from "../../features/instructions/InstructionAudio";
import { label, LoadError, StepHeader, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, translateFieldCodes } from "../../i18n/errors";

/**
 * Screen 3 — choose where you work: a city and the catalog areas the worker will travel to.
 * No browser location or GPS is requested.
 */
export function OnboardingAreasPage() {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const base = useLoad((signal) => Promise.all([workersApi.fetchWorker(signal), catalogApi.fetchAreas(signal)]));
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

  const allAreas = base.state.status === "ready" ? base.state.data[1].results : [];
  const cities = useMemo(() => {
    const seen = new Map<string, catalogApi.City>();
    for (const area of allAreas) if (!seen.has(area.city.code)) seen.set(area.city.code, area.city);
    return [...seen.values()].sort((a, b) => a.sort_order - b.sort_order);
  }, [allAreas]);

  if (base.state.status === "loading") return <PageLoader />;
  if (base.state.status === "error") return <LoadError error={base.state.error} onRetry={base.retry} />;
  // Screens are completed in order: resume at the work step if it is not done.
  if (!base.state.data[0].onboarding.steps.work.complete) return <Navigate to={PATHS.workerWork} replace />;

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

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setErrorCodes({});
    setSaving(true);
    try {
      const result = await workersApi.saveAreas({ city: selectedCity ?? "", service_areas: areas });
      navigate(result.onboarding.next_step === "work" ? PATHS.workerWork : PATHS.worker);
    } catch (error) {
      setErrorCodes(fieldErrorCodes(error));
      setFormError(error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} noValidate className="space-y-6">
      <StepHeader step={3} title={t("onboarding.areas.title")} />
      <InstructionAudio id="onboarding_areas" />
      <p className="text-muted">{t("onboarding.areas.explain")}</p>
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

      <div className="grid gap-3">
        <Button type="submit" fullWidth loading={saving} loadingLabel={t("onboarding.saving")} icon={<Save className="size-5" aria-hidden />}>
          {t("onboarding.areas.save")}
        </Button>
        <ButtonLink to={PATHS.workerWork} variant="secondary" fullWidth icon={<ArrowLeft className="size-5 rtl:-scale-x-100" aria-hidden />}>
          {t("common.back")}
        </ButtonLink>
      </div>
    </form>
  );
}
