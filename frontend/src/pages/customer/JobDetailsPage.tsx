import { ArrowRight, Building2, ChevronDown, Clock, Lock, MapPin, Save } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import { ApiError } from "../../api/client";
import * as jobsApi from "../../api/jobs";
import { CatalogIcon } from "../../components/catalogIcons";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { IconTileGroup, type TileOption } from "../../components/ui/IconTile";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { TextField } from "../../components/ui/TextField";
import { citiesOf, type JobCatalog, loadJobCatalog } from "../../features/jobs/catalog";
import { OriginalInput } from "../../features/jobs/JobSummary";
import { JobPhotos } from "../../features/jobs/JobPhotos";
import { textDir } from "../../features/jobs/text";
import { UrduDescriptionEditor } from "../../features/jobs/UrduDescription";
import { fromIso, karachiDate, toIso } from "../../features/jobs/time";
import { SimulatedBadge } from "../../features/voice/SimulatedBadge";
import { label, LoadError, StepHeader, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, LocalMessage, translateFieldCodes } from "../../i18n/errors";

/** Step 2 — review and choose the details. Loads the saved draft; AI suggestions are only prefills. */
export function JobDetailsPage() {
  const { id = "" } = useParams();
  const data = useLoad((signal) => Promise.all([jobsApi.fetchJob(id, signal), loadJobCatalog(signal)]), [id]);
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [job, catalog] = data.state.data;
  if (job.status !== "draft") return <Navigate to={`/customer/requests/${job.id}`} replace />;
  return <DetailsForm key={job.id} job={job} catalog={catalog} />;
}

function DetailsForm({ job, catalog }: { job: jobsApi.JobRequest; catalog: JobCatalog }) {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const d = job.details;
  const start = fromIso(d.window_start);
  const end = fromIso(d.window_end);
  const [description, setDescription] = useState(d.description);
  // Urdu version for the worker (English / Roman Urdu / mixed requests): reviewed and approved by the customer.
  const showUrdu = job.urdu.needed || Boolean(job.urdu.text);
  const [urduText, setUrduText] = useState(job.urdu.text);
  const [urduApproved, setUrduApproved] = useState(job.urdu.status === "approved");
  const [trade, setTrade] = useState<string[]>(d.trade ? [d.trade] : []);
  const [services, setServices] = useState<string[]>(d.services);
  const [excluded, setExcluded] = useState<string[]>(d.services_excluded);
  const [city, setCity] = useState<string[]>(d.city ? [d.city] : []);
  const [area, setArea] = useState<string[]>(d.area ? [d.area] : []);
  const [date, setDate] = useState(start.date);
  const [startTime, setStartTime] = useState(start.time);
  const [endTime, setEndTime] = useState(end.time);
  const [address, setAddress] = useState(d.address_private);
  const [access, setAccess] = useState(d.access_notes);
  const [budget, setBudget] = useState(d.budget_pkr ? String(Number(d.budget_pkr)) : "");
  const [photos, setPhotos] = useState(job.photos);
  const [busy, setBusy] = useState<"save" | "continue" | null>(null);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [codes, setCodes] = useState<Record<string, string[]>>({});
  const errors = translateFieldCodes(codes, t);

  const suggestions = job.suggestions;
  const check = (name: string) => Boolean(suggestions && (suggestions.uncertain.includes(name) || suggestions.missing.includes(name)));
  const checkBadge = (name: string) => check(name) && <StatusBadge tone="warning">{t("voice.pleaseCheck")}</StatusBadge>;

  const selectedTrade = trade[0];
  const tradeServices = catalog.services.filter((service) => service.trade === selectedTrade);
  const serviceOption = (service: (typeof tradeServices)[number]): TileOption<string> => ({
    value: service.code,
    label: label(service.labels, language),
    icon: <CatalogIcon id={service.icon} className="size-7" />,
  });
  const tradeOptions: TileOption<string>[] = catalog.trades.map((item) => ({
    value: item.code,
    label: label(item.labels, language),
    icon: <CatalogIcon id={item.icon} className="size-9" />,
  }));
  const cityOptions: TileOption<string>[] = citiesOf(catalog).map((item) => ({
    value: item.code,
    label: label(item.labels, language),
    icon: <Building2 className="size-7" aria-hidden />,
  }));
  const areaOptions: TileOption<string>[] = catalog.areas
    .filter((item) => item.city.code === city[0])
    .map((item) => ({ value: item.code, label: label(item.labels, language), icon: <MapPin className="size-6" aria-hidden /> }));

  function changeTrade(next: string[]) {
    setTrade(next);
    const allowed = new Set(catalog.services.filter((service) => service.trade === next[0]).map((service) => service.code));
    setServices((current) => current.filter((code) => allowed.has(code)));
    setExcluded((current) => current.filter((code) => allowed.has(code)));
  }
  function changeServices(next: string[]) {
    setServices(next);
    setExcluded((current) => current.filter((code) => !next.includes(code)));
  }
  function changeCity(next: string[]) {
    setCity(next);
    const inCity = new Set(catalog.areas.filter((item) => item.city.code === next[0]).map((item) => item.code));
    setArea((current) => current.filter((code) => inCity.has(code)));
  }

  function payload(): jobsApi.DetailsPatch | LocalMessage {
    const anyTime = date || startTime || endTime;
    if (anyTime && !(date && startTime && endTime)) return new LocalMessage("jobs.time.incomplete");
    if (budget && !/^\d{1,8}(\.\d{1,2})?$/.test(budget.trim())) return new LocalMessage("jobs.budget.invalid");
    return {
      description: description.trim(),
      trade: selectedTrade ?? null,
      services,
      services_excluded: excluded,
      city: city[0] ?? null,
      area: area[0] ?? null,
      window_start: anyTime ? toIso(date, startTime) : null,
      window_end: anyTime ? toIso(date, endTime) : null,
      address_private: address.trim(),
      access_notes: access.trim(),
      budget_pkr: budget.trim() ? budget.trim() : null,
      ...(showUrdu ? { description_ur: urduText.trim(), description_ur_approved: urduApproved } : {}),
    };
  }

  function changeDescription(value: string) {
    setDescription(value);
    // The Urdu version was approved for the previous wording: it must be checked again.
    if (urduApproved && value.trim() !== d.description.trim()) setUrduApproved(false);
  }

  async function save(next: "save" | "continue") {
    setFailure(null);
    setCodes({});
    setSaved(false);
    const body = payload();
    if (body instanceof LocalMessage) {
      setFailure(body);
      setCodes(body.key === "jobs.time.incomplete" ? { window_start: ["required"] } : { budget_pkr: ["invalid"] });
      return;
    }
    setBusy(next);
    try {
      await jobsApi.saveJob(job.id, body);
      if (next === "continue") navigate(`/customer/requests/${job.id}/review`);
      else setSaved(true);
    } catch (error) {
      setCodes(fieldErrorCodes(error));
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void save("continue");
  }

  const timeErrors = [...(errors.window_start ?? []), ...(errors.window_end ?? [])];
  const minDate = karachiDate(0);
  const maxDate = karachiDate(90);

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-5">
      <StepHeader step={2} flow="request" title={t("jobs.details.title")} />
      <p className="text-muted">{t("jobs.details.intro")}</p>

      {suggestions && (
        <div className="flex flex-wrap items-center gap-2">
          <SimulatedBadge show={suggestions.simulated} />
          <span className="text-sm text-muted">{t("jobs.details.suggestionsNote")}</span>
        </div>
      )}
      <OriginalInput job={job} />
      {suggestions && suggestions.unmatched_mentions.length > 0 && (
        <Alert tone="info" title={t("voice.unmatchedTitle")}>
          <ul className="list-inside list-disc">
            {suggestions.unmatched_mentions.map((mention) => (
              <li key={mention.phrase} dir={textDir(mention.phrase)}>
                “{mention.phrase}”{mention.negated && ` — ${t("voice.mentionNegated")}`}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      {saved && <Alert tone="success">{t("jobs.details.saved")}</Alert>}

      <div className="grid items-start gap-5 xl:grid-cols-2">
      <div className="card min-w-0 space-y-6 p-4 sm:p-6">

      <div className="space-y-1">
        <TextArea label={t("jobs.field.description")} hint={t("jobs.field.descriptionHint")} value={description} onChange={changeDescription} errors={errors.description} maxLength={2000} rows={4} dir={textDir(description)} />
        {checkBadge("description")}
      </div>
      {showUrdu && (
        <UrduDescriptionEditor urdu={job.urdu} text={urduText} approved={urduApproved} onText={setUrduText} onApproved={setUrduApproved}
          errors={errors.description_ur} />
      )}

      <div className="space-y-1">
        {checkBadge("trade")}
        <IconTileGroup label={t("jobs.field.trade")} mode="single" options={tradeOptions} value={trade} onChange={changeTrade} errors={errors.trade} />
      </div>

      {selectedTrade && (
        <div className="space-y-1">
          {checkBadge("services")}
          <IconTileGroup label={t("jobs.field.services")} mode="multiple" options={tradeServices.map(serviceOption)} value={services} onChange={changeServices} errors={errors.services} />
          <details className="group rounded-2xl border border-line bg-white p-3" open={excluded.length > 0 || Boolean(errors.services_excluded)}>
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 font-bold text-primary">
              {t("onboarding.work.moreOptions")}
              <ChevronDown className="size-5 transition-transform group-open:rotate-180" aria-hidden />
            </summary>
            <div className="mt-3">
              <IconTileGroup
                label={t("jobs.field.notNeeded")}
                mode="multiple"
                options={tradeServices.filter((service) => !services.includes(service.code)).map(serviceOption)}
                value={excluded}
                onChange={setExcluded}
                errors={errors.services_excluded}
              />
            </div>
          </details>
        </div>
      )}

      <div className="space-y-1">
        {checkBadge("area")}
        <IconTileGroup label={t("jobs.field.city")} mode="single" options={cityOptions} value={city} onChange={changeCity} errors={errors.city} />
      </div>
      {city[0] && <IconTileGroup label={t("jobs.field.area")} mode="single" options={areaOptions} value={area} onChange={setArea} errors={errors.area} />}

      </div>
      <div className="card min-w-0 space-y-6 p-4 sm:p-6">
      <fieldset className="space-y-3">
        <legend className="flex items-center gap-2 px-1 font-bold">
          <Clock className="size-5" aria-hidden />
          {t("jobs.field.when")}
        </legend>
        {d.preferred_time_text && (
          <Alert tone="warning" title={t("jobs.time.youSaid", { phrase: d.preferred_time_text })}>
            {t("jobs.time.choosePrompt")}
          </Alert>
        )}
        <p className="text-sm text-muted">{t("jobs.time.zoneNote")}</p>
        <TextField label={t("jobs.field.date")} type="date" value={date} onChange={setDate} min={minDate} max={maxDate} dir="ltr" />
        <div className="grid max-w-md grid-cols-2 gap-3">
          <TextField label={t("jobs.field.startTime")} type="time" value={startTime} onChange={setStartTime} dir="ltr" />
          <TextField label={t("jobs.field.endTime")} type="time" value={endTime} onChange={setEndTime} dir="ltr" />
        </div>
        {timeErrors.length > 0 && (
          <ul className="text-sm font-bold text-danger-strong">
            {timeErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}
      </fieldset>

      <fieldset className="space-y-3 rounded-2xl border border-dashed border-line bg-surface p-4">
        <legend className="flex items-center gap-2 px-1 font-bold">
          <Lock className="size-5" aria-hidden />
          {t("jobs.private.heading")}
        </legend>
        <p className="text-sm text-muted">{t("jobs.private.note")}</p>
        <TextArea label={t("jobs.field.address")} value={address} onChange={setAddress} errors={errors.address_private} maxLength={500} rows={2} dir={textDir(address)} />
        <TextArea label={t("jobs.field.access")} hint={t("jobs.field.accessHint")} value={access} onChange={setAccess} errors={errors.access_notes} maxLength={500} rows={2} dir={textDir(access)} />
      </fieldset>

      <TextField
        label={t("jobs.field.budget")}
        hint={t("jobs.budget.note")}
        value={budget}
        onChange={setBudget}
        errors={errors.budget_pkr}
        inputMode="decimal"
        dir="ltr"
        maxLength={12}
      />

      <section aria-labelledby="photos-heading" className="space-y-2">
        <h2 id="photos-heading" className="font-bold">{t("jobs.field.photos")}</h2>
        <p className="text-sm text-muted">{t("jobs.photos.note")}</p>
        <JobPhotos jobId={job.id} photos={photos} editable onChange={setPhotos} />
      </section>

      </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="submit" className="sm:min-w-56" loading={busy === "continue"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />}>
          {t("jobs.details.toReview")}
        </Button>
        <Button variant="secondary" loading={busy === "save"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Save className="size-5" aria-hidden />} onClick={() => void save("save")}>
          {t("jobs.details.saveDraft")}
        </Button>
      </div>
      {failure instanceof ApiError && failure.status === 409 && <p className="text-sm text-muted">{t("errors.request_not_editable")}</p>}
    </form>
  );
}
