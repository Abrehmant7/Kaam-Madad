import { Ban, Banknote, BadgeCheck, Hash, type LucideIcon, Package, PackageCheck, PackagePlus, PackageX, Search, UserRound, Wrench } from "lucide-react";
import { useState } from "react";

import type { Materials, QuoteTerms, VisitFeeTreatment } from "../../api/conversations";
import { IconTileGroup } from "../../components/ui/IconTile";
import { TextArea } from "../../components/ui/TextArea";
import { TextField } from "../../components/ui/TextField";
import { useI18n } from "../../i18n/context";
import { textDir } from "../jobs/text";
import { fromIso, karachiDate, toIso } from "../jobs/time";

const MATERIALS: Materials[] = ["included", "worker_extra", "customer", "none"];
const VISIT: VisitFeeTreatment[] = ["none", "charged", "waived_if_hired", "included"];
const ICONS: Record<string, LucideIcon> = {
  total: Package, per_item: Hash,
  included: PackageCheck, worker_extra: PackagePlus, customer: UserRound, none: PackageX,
  charged: Banknote, waived_if_hired: BadgeCheck,
};
const VISIT_ICONS: Record<string, LucideIcon> = { none: Ban, included: PackageCheck };

/** Any source of initial terms: a quote draft, a submitted quote or a booking's terms in effect. */
type Initial = Partial<Omit<QuoteTerms, "start_at" | "end_at">> & { start_at?: string | null; end_at?: string | null };

const plain = (value: string | null | undefined) => (value ? String(Number(value)) : "");
const amount = (value: string) => value.trim() || null; // the server validates the format

/** Editable structured terms (QT-01), shared by the quote form and booking change proposals. */
export function useTerms(initial: Initial | null) {
  const s = fromIso(initial?.start_at ?? null);
  const e = fromIso(initial?.end_at ?? null);
  const [inspection, setInspection] = useState<("no" | "yes")[]>([initial?.inspection_only ? "yes" : "no"]);
  const [scope, setScope] = useState(initial?.scope ?? "");
  const [quantity, setQuantity] = useState(initial?.quantity ? String(initial.quantity) : "");
  const [labour, setLabour] = useState(plain(initial?.labour_amount));
  const [basis, setBasis] = useState<("total" | "per_item")[]>([initial?.labour_basis ?? "total"]);
  const [materials, setMaterials] = useState<Materials[]>(initial?.materials ? [initial.materials] : []);
  const [materialsAmount, setMaterialsAmount] = useState(plain(initial?.materials_amount));
  const [visitFee, setVisitFee] = useState(plain(initial?.visit_fee));
  const [visit, setVisit] = useState<VisitFeeTreatment[]>([initial?.visit_fee_treatment ?? "none"]);
  const [exclusions, setExclusions] = useState(initial?.exclusions ?? "");
  const [date, setDate] = useState(s.date);
  const [startTime, setStartTime] = useState(s.time);
  const [endTime, setEndTime] = useState(e.time);

  const inspectionOnly = inspection[0] === "yes";
  function terms(): QuoteTerms {
    return {
      inspection_only: inspectionOnly,
      scope: scope.trim(),
      quantity: quantity.trim() ? Number(quantity) : null,
      labour_amount: amount(labour),
      labour_basis: basis[0] ?? "total",
      materials: materials[0] ?? null,
      materials_amount: materials[0] === "worker_extra" ? amount(materialsAmount) : null,
      visit_fee: amount(visitFee),
      visit_fee_treatment: visit[0] ?? "none",
      exclusions: exclusions.trim(),
      start_at: date && startTime ? toIso(date, startTime) : null,
      end_at: date && endTime ? toIso(date, endTime) : null,
    };
  }
  return {
    terms, inspectionOnly,
    fields: { inspection, setInspection, scope, setScope, quantity, setQuantity, labour, setLabour, basis, setBasis, materials,
              setMaterials, materialsAmount, setMaterialsAmount, visitFee, setVisitFee, visit, setVisit, exclusions,
              setExclusions, date, setDate, startTime, setStartTime, endTime, setEndTime },
  };
}

export type TermsState = ReturnType<typeof useTerms>;

export function TermsFields({ state, errors, allowInspection = true, allowTime = true }: {
  state: TermsState; errors: (name: string) => string[]; allowInspection?: boolean; allowTime?: boolean;
}) {
  const { t, language } = useI18n();
  const f = state.fields;
  const tile = <V extends string>(values: V[], prefix: string, icons: Record<string, LucideIcon> = ICONS) =>
    values.map((value) => {
      const Icon = icons[value] ?? ICONS[value] ?? Package;
      return { value, label: t(`${prefix}.${value}` as never), icon: <Icon className="size-6" aria-hidden /> };
    });
  const dir = (value: string) => (value ? textDir(value) : language === "ur" ? "rtl" : "ltr");

  return (
    <>
      {allowInspection && (
        <IconTileGroup label={t("quote.form.inspectionOnly")} mode="single" columns={2} value={f.inspection} onChange={f.setInspection}
          options={[{ value: "no", label: t("quote.form.fullJob"), icon: <Wrench className="size-6" aria-hidden /> },
                    { value: "yes", label: t("quote.form.inspection"), icon: <Search className="size-6" aria-hidden /> }]} />
      )}
      <TextArea label={t("quote.field.scope")} value={f.scope} onChange={f.setScope} errors={errors("scope")} rows={3} maxLength={1000} dir={dir(f.scope)} />

      {!state.inspectionOnly && (
        <>
          <IconTileGroup label={t("quote.form.basis")} mode="single" options={tile<"total" | "per_item">(["total", "per_item"], "quote.basis")}
            value={f.basis} onChange={f.setBasis} />
          <div className="grid grid-cols-2 gap-3">
            <TextField label={t("quote.form.labourAmount")} value={f.labour} onChange={f.setLabour} errors={errors("labour_amount")} inputMode="decimal" dir="ltr" maxLength={12} />
            <TextField label={t("quote.field.quantity")} value={f.quantity} onChange={f.setQuantity} errors={errors("quantity")} inputMode="numeric" dir="ltr" maxLength={3} />
          </div>
          <IconTileGroup label={t("quote.field.materials")} mode="single" columns={1} options={tile(MATERIALS, "quote.materials")}
            value={f.materials} onChange={f.setMaterials} errors={errors("materials")} />
          {f.materials[0] === "worker_extra" && (
            <TextField label={t("quote.form.materialsAmount")} hint={t("quote.form.materialsAmountHint")} value={f.materialsAmount}
              onChange={f.setMaterialsAmount} errors={errors("materials_amount")} inputMode="decimal" dir="ltr" maxLength={12} />
          )}
        </>
      )}

      <IconTileGroup label={t("quote.field.visit")} mode="single" columns={1} options={tile(VISIT, "quote.visit", VISIT_ICONS)}
        value={f.visit} onChange={f.setVisit} errors={errors("visit_fee_treatment")} />
      {f.visit[0] !== "none" && f.visit[0] !== "included" && (
        <TextField label={t("quote.form.visitFee")} value={f.visitFee} onChange={f.setVisitFee} errors={errors("visit_fee")} inputMode="decimal" dir="ltr" maxLength={12} />
      )}
      <TextArea label={t("quote.field.exclusions")} hint={t("quote.form.exclusionsHint")} value={f.exclusions} onChange={f.setExclusions}
        rows={2} maxLength={500} dir={dir(f.exclusions)} />

      {allowTime ? (
        <fieldset className="space-y-3">
          <legend className="font-bold">{t("quote.field.when")}</legend>
          <p className="text-sm text-muted">{t("jobs.time.zoneNote")}</p>
          <TextField label={t("jobs.field.date")} type="date" value={f.date} onChange={f.setDate} min={karachiDate(0)} max={karachiDate(90)} dir="ltr" />
          <div className="grid grid-cols-2 gap-3">
            <TextField label={t("jobs.field.startTime")} type="time" value={f.startTime} onChange={f.setStartTime} errors={errors("start_at")} dir="ltr" />
            <TextField label={t("jobs.field.endTime")} type="time" value={f.endTime} onChange={f.setEndTime} errors={errors("end_at")} dir="ltr" />
          </div>
        </fieldset>
      ) : (
        <p className="text-sm text-muted">{t("booking.change.timeLocked")}</p>
      )}
    </>
  );
}
