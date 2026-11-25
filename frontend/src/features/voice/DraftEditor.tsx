import { CircleHelp, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { Area, ServiceTag, Trade } from "../../api/catalog";
import type { Draft, DraftFields, VoiceKind } from "../../api/voice";
import { CatalogIcon } from "../../components/catalogIcons";
import { IconTileGroup } from "../../components/ui/IconTile";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { FieldErrors, TextField } from "../../components/ui/TextField";
import { isTranslationKey, useI18n } from "../../i18n/context";

export interface CatalogData {
  trades: Trade[];
  services: ServiceTag[];
  areas: Area[];
}

interface DraftEditorProps {
  kind: VoiceKind;
  draft: Draft;
  fields: DraftFields;
  onChange: (fields: DraftFields) => void;
  catalog: CatalogData;
  errors: Record<string, string[]>;
  disabled?: boolean;
}

/**
 * Review and correct an AI draft. Every value is editable; missing and uncertain
 * fields are marked (text + icon, not colour alone); unmatched phrases are shown
 * with their negation so nothing said is silently dropped or flipped.
 */
export function DraftEditor({ kind, draft, fields, onChange, catalog, errors, disabled = false }: DraftEditorProps) {
  const { t, language } = useI18n();
  const set = (patch: DraftFields) => onChange({ ...fields, ...patch });
  const fieldLabel = (name: string) => {
    const key = `voice.field.${name}`;
    return isTranslationKey(key) ? t(key) : name;
  };
  const trade = fields.trade ?? null;
  const tradeServices = catalog.services.filter((service) => !trade || service.trade === trade);

  function marker(name: string): ReactNode {
    if (draft.missing.includes(name) && isEmpty(fields[name as keyof DraftFields])) {
      return <StatusBadge tone="danger" icon={<TriangleAlert className="size-4" aria-hidden />}>{t("voice.missing")}</StatusBadge>;
    }
    if (draft.uncertain.includes(name)) {
      return <StatusBadge tone="warning" icon={<CircleHelp className="size-4" aria-hidden />}>{t("voice.pleaseCheck")}</StatusBadge>;
    }
    return null;
  }

  function heard(name: string): ReactNode {
    const phrase = draft.heard[name];
    return phrase ? <p className="text-sm text-muted">{t("voice.heard", { phrase })}</p> : null;
  }

  const serviceOptions = tradeServices.map((service) => ({
    value: service.code,
    label: service.labels[language],
    icon: <CatalogIcon id={service.icon} className="size-6" />,
  }));
  const [positiveKey, negativeKey] =
    kind === "worker_introduction" ? (["services_offered", "services_not_offered"] as const) : (["services", "services_excluded"] as const);
  const positive = fields[positiveKey] ?? [];
  const negative = fields[negativeKey] ?? [];
  const overlap = positive.filter((code) => negative.includes(code));

  const textField = (name: "name" | "preferred_time_text", maxLength: number) => (
    <Section label={fieldLabel(name)} marker={marker(name)}>
      <TextField
        label={fieldLabel(name)}
        value={fields[name] ?? ""}
        onChange={(value) => set({ [name]: value || null })}
        errors={errors[name]}
        maxLength={maxLength}
        disabled={disabled}
        dir="auto"
      />
      {heard(name)}
    </Section>
  );

  const numberField = (name: "years_experience" | "budget_pkr") => (
    <Section label={fieldLabel(name)} marker={marker(name)}>
      <TextField
        label={fieldLabel(name)}
        value={fields[name] === null || fields[name] === undefined ? "" : String(fields[name])}
        onChange={(value) => {
          const digits = value.replace(/[^\d]/g, "");
          set({ [name]: digits === "" ? null : Number(digits) });
        }}
        errors={errors[name]}
        inputMode="numeric"
        dir="ltr"
        disabled={disabled}
      />
    </Section>
  );

  return (
    <div className="space-y-5">
      {kind === "worker_introduction" ? textField("name", 80) : (
        <Section label={t("voice.field.description")} marker={marker("description")}>
          <TextArea
            label={t("voice.field.description")}
            value={fields.description ?? ""}
            onChange={(value) => set({ description: value || null })}
            errors={errors.description}
            maxLength={1000}
            disabled={disabled}
          />
        </Section>
      )}

      <Section label={t("voice.field.trade")} marker={marker("trade")}>
        <IconTileGroup
          label={t("voice.field.trade")}
          mode="single"
          options={catalog.trades.map((item) => ({
            value: item.code,
            label: item.labels[language],
            icon: <CatalogIcon id={item.icon} />,
          }))}
          value={trade ? [trade] : []}
          onChange={([value]) => set({ trade: value ?? null })}
          errors={errors.trade}
        />
        {heard("trade")}
      </Section>

      {kind === "worker_introduction" && numberField("years_experience")}

      <Section label={fieldLabel(positiveKey)} marker={marker(positiveKey)}>
        <IconTileGroup
          label={fieldLabel(positiveKey)}
          mode="multiple"
          options={serviceOptions}
          value={positive}
          onChange={(value) => set({ [positiveKey]: value })}
          errors={errors[positiveKey]}
        />
      </Section>

      <Section label={fieldLabel(negativeKey)} marker={marker(negativeKey)}>
        <IconTileGroup
          label={fieldLabel(negativeKey)}
          mode="multiple"
          options={serviceOptions}
          value={negative}
          onChange={(value) => set({ [negativeKey]: value })}
          errors={errors[negativeKey]}
        />
        {overlap.length > 0 && (
          <p role="alert" className="text-sm font-bold text-danger-strong">
            {t("voice.overlap")}
          </p>
        )}
      </Section>

      {kind === "job_description" && (
        <>
          <Section label={t("voice.field.area")} marker={marker("area")}>
            <AreaSelect
              areas={catalog.areas}
              value={fields.area ?? null}
              onChange={(area) => set({ area })}
              errors={errors.area ?? []}
              disabled={disabled}
            />
            {heard("area")}
          </Section>
          {textField("preferred_time_text", 120)}
          {numberField("budget_pkr")}
        </>
      )}

      {draft.unmatched_mentions.length > 0 && (
        <section className="space-y-2 rounded-xl border border-warning/50 bg-warning-soft p-3">
          <h3 className="font-bold text-warning-strong">{t("voice.unmatchedTitle")}</h3>
          <p className="text-sm">{t("voice.unmatchedHelp")}</p>
          <ul className="space-y-1">
            {draft.unmatched_mentions.map((mention) => (
              <li key={`${mention.phrase}-${mention.negated}`} className="flex flex-wrap items-center gap-2">
                <bdi className="font-bold">“{mention.phrase}”</bdi>
                <StatusBadge tone={mention.negated ? "danger" : "info"}>
                  {mention.negated ? t("voice.mentionNegated") : t("voice.mentionPositive")}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
}

function Section({ label, marker, children }: { label: string; marker: ReactNode; children: ReactNode }) {
  return (
    <div className="space-y-2" data-field={label}>
      {marker && <div>{marker}</div>}
      {children}
    </div>
  );
}

function AreaSelect({ areas, value, onChange, errors, disabled }: {
  areas: Area[];
  value: string | null;
  onChange: (value: string | null) => void;
  errors: string[];
  disabled: boolean;
}) {
  const { t, language } = useI18n();
  const cities = Array.from(new Map(areas.map((area) => [area.city.code, area.city])).values());
  return (
    <div>
      <label htmlFor="voice-area" className="mb-1 block font-bold">
        {t("voice.field.area")}
      </label>
      <select
        id="voice-area"
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        aria-invalid={errors.length > 0 || undefined}
        aria-describedby={errors.length ? "voice-area-errors" : undefined}
        className="min-h-12 w-full rounded-xl border-2 border-line bg-white px-3 text-lg"
      >
        <option value="">{t("voice.chooseArea")}</option>
        {cities.map((city) => (
          <optgroup key={city.code} label={city.labels[language]}>
            {areas
              .filter((area) => area.city.code === city.code)
              .map((area) => (
                <option key={area.code} value={area.code}>
                  {area.labels[language]}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      <FieldErrors id="voice-area-errors" messages={errors} />
    </div>
  );
}
