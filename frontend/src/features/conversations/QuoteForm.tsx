import { Ban, Banknote, BadgeCheck, Hash, type LucideIcon, Package, PackageCheck, PackagePlus, PackageX, Save, Search, Send, Trash2, UserRound, Wrench } from "lucide-react";
import { useState } from "react";

import * as convApi from "../../api/conversations";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { TextArea } from "../../components/ui/TextArea";
import { TextField } from "../../components/ui/TextField";
import { useI18n } from "../../i18n/context";
import { describeError, fieldErrorCodes, fieldErrorText } from "../../i18n/errors";
import { textDir } from "../jobs/text";
import { fromIso, karachiDate, toIso } from "../jobs/time";
import { money } from "./quoteText";

const MATERIALS: convApi.Materials[] = ["included", "worker_extra", "customer", "none"];
const VISIT: convApi.VisitFeeTreatment[] = ["none", "charged", "waived_if_hired", "included"];
const ICONS: Record<string, LucideIcon> = {
  total: Package, per_item: Hash,
  included: PackageCheck, worker_extra: PackagePlus, customer: UserRound, none: PackageX,
  charged: Banknote, waived_if_hired: BadgeCheck,
};
const VISIT_ICONS: Record<string, LucideIcon> = { none: Ban, included: PackageCheck };

/** The worker's structured quote. The server validates, computes totals and freezes each submitted version. */
export function QuoteForm({ invitationId, start, onDone }: { invitationId: string; start: convApi.Quote | null; onDone: () => void }) {
  const { t, language } = useI18n();
  const s = fromIso(start?.start_at ?? null);
  const e = fromIso(start?.end_at ?? null);
  const [inspection, setInspection] = useState<("no" | "yes")[]>([start?.inspection_only ? "yes" : "no"]);
  const [scope, setScope] = useState(start?.scope ?? "");
  const [quantity, setQuantity] = useState(start?.quantity ? String(start.quantity) : "");
  const [labour, setLabour] = useState(start?.labour_amount ? String(Number(start.labour_amount)) : "");
  const [basis, setBasis] = useState<("total" | "per_item")[]>([start?.labour_basis ?? "total"]);
  const [materials, setMaterials] = useState<convApi.Materials[]>(start?.materials ? [start.materials] : []);
  const [materialsAmount, setMaterialsAmount] = useState(start?.materials_amount ? String(Number(start.materials_amount)) : "");
  const [visitFee, setVisitFee] = useState(start?.visit_fee ? String(Number(start.visit_fee)) : "");
  const [visit, setVisit] = useState<convApi.VisitFeeTreatment[]>([start?.visit_fee_treatment ?? "none"]);
  const [exclusions, setExclusions] = useState(start?.exclusions ?? "");
  const [date, setDate] = useState(s.date);
  const [startTime, setStartTime] = useState(s.time);
  const [endTime, setEndTime] = useState(e.time);
  const [saved, setSaved] = useState<convApi.Quote | null>(start?.status === "draft" ? start : null);
  const [busy, setBusy] = useState<"save" | "submit" | "discard" | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [codes, setCodes] = useState<Record<string, string[]>>({});

  const inspectionOnly = inspection[0] === "yes";
  const issues = { ...(saved?.issues ?? {}), ...codes };
  const errors = (name: string) => (issues[name] ?? []).map((code) => fieldErrorText(code, t));
  const amount = (value: string) => value.trim() || null; // the server validates the format

  function terms(): convApi.QuoteTerms {
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

  async function run(kind: NonNullable<typeof busy>) {
    setFailure(null);
    setCodes({});
    setBusy(kind);
    try {
      if (kind === "discard") {
        await convApi.deleteDraft(invitationId);
        onDone();
        return;
      }
      const body = terms();
      const draft = await convApi.saveDraft(invitationId, body);
      setSaved(draft);
      if (kind === "submit") {
        await convApi.submitDraft(invitationId);
        onDone();
      }
    } catch (error) {
      setCodes(fieldErrorCodes(error));
      setFailure(error);
    } finally {
      setBusy(null);
    }
  }

  const tile = <V extends string>(values: V[], prefix: string, icons: Record<string, LucideIcon> = ICONS) =>
    values.map((value) => {
      const Icon = icons[value] ?? ICONS[value] ?? Package;
      return { value, label: t(`${prefix}.${value}` as never), icon: <Icon className="size-6" aria-hidden /> };
    });

  return (
    <section aria-labelledby="quote-form-heading" className="space-y-4 rounded-2xl border-2 border-primary/40 bg-white p-4">
      <h3 id="quote-form-heading" className="text-lg font-bold">{t("quote.form.title")}</h3>
      <p className="text-sm text-muted">{t("quote.form.intro")}</p>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}

      <IconTileGroup label={t("quote.form.inspectionOnly")} mode="single" columns={2} value={inspection} onChange={setInspection}
        options={[{ value: "no", label: t("quote.form.fullJob"), icon: <Wrench className="size-6" aria-hidden /> },
                  { value: "yes", label: t("quote.form.inspection"), icon: <Search className="size-6" aria-hidden /> }]} />
      <TextArea label={t("quote.field.scope")} value={scope} onChange={setScope} errors={errors("scope")} rows={3} maxLength={1000} dir={scope ? textDir(scope) : language === "ur" ? "rtl" : "ltr"} />

      {!inspectionOnly && (
        <>
          <IconTileGroup label={t("quote.form.basis")} mode="single" options={tile<"total" | "per_item">(["total", "per_item"], "quote.basis")} value={basis} onChange={setBasis} />
          <div className="grid grid-cols-2 gap-3">
            <TextField label={t("quote.form.labourAmount")} value={labour} onChange={setLabour} errors={errors("labour_amount")} inputMode="decimal" dir="ltr" maxLength={12} />
            <TextField label={t("quote.field.quantity")} value={quantity} onChange={setQuantity} errors={errors("quantity")} inputMode="numeric" dir="ltr" maxLength={3} />
          </div>
          <IconTileGroup label={t("quote.field.materials")} mode="single" columns={1} options={tile(MATERIALS, "quote.materials")} value={materials} onChange={setMaterials} errors={errors("materials")} />
          {materials[0] === "worker_extra" && (
            <TextField label={t("quote.form.materialsAmount")} hint={t("quote.form.materialsAmountHint")} value={materialsAmount} onChange={setMaterialsAmount}
              errors={errors("materials_amount")} inputMode="decimal" dir="ltr" maxLength={12} />
          )}
        </>
      )}

      <IconTileGroup label={t("quote.field.visit")} mode="single" columns={1} options={tile(VISIT, "quote.visit", VISIT_ICONS)} value={visit} onChange={setVisit} errors={errors("visit_fee_treatment")} />
      {visit[0] !== "none" && visit[0] !== "included" && (
        <TextField label={t("quote.form.visitFee")} value={visitFee} onChange={setVisitFee} errors={errors("visit_fee")} inputMode="decimal" dir="ltr" maxLength={12} />
      )}
      <TextArea label={t("quote.field.exclusions")} hint={t("quote.form.exclusionsHint")} value={exclusions} onChange={setExclusions} rows={2} maxLength={500}
        dir={exclusions ? textDir(exclusions) : language === "ur" ? "rtl" : "ltr"} />

      <fieldset className="space-y-3">
        <legend className="font-bold">{t("quote.field.when")}</legend>
        <p className="text-sm text-muted">{t("jobs.time.zoneNote")}</p>
        <TextField label={t("jobs.field.date")} type="date" value={date} onChange={setDate} min={karachiDate(0)} max={karachiDate(90)} dir="ltr" />
        <div className="grid grid-cols-2 gap-3">
          <TextField label={t("jobs.field.startTime")} type="time" value={startTime} onChange={setStartTime} errors={errors("start_at")} dir="ltr" />
          <TextField label={t("jobs.field.endTime")} type="time" value={endTime} onChange={setEndTime} errors={errors("end_at")} dir="ltr" />
        </div>
      </fieldset>

      {saved?.totals && (
        <p className="rounded-xl bg-surface p-3 font-bold">
          {t("quote.field.total")}: <bdi dir="ltr">{money(saved.totals.known_total)}</bdi>
          {!saved.totals.complete && <span className="font-normal"> {t("quote.plusUnknown")}</span>}
        </p>
      )}
      <p className="text-sm text-muted">{t("quote.form.submitNote")}</p>
      <div className="grid gap-2">
        <Button fullWidth loading={busy === "submit"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Send className="size-5" aria-hidden />} onClick={() => void run("submit")}>
          {t("quote.form.submit")}
        </Button>
        <Button variant="secondary" fullWidth loading={busy === "save"} loadingLabel={t("onboarding.saving")} disabled={busy !== null} icon={<Save className="size-5" aria-hidden />} onClick={() => void run("save")}>
          {t("quote.form.saveDraft")}
        </Button>
        {saved && (
          <Button variant="ghost" disabled={busy !== null} icon={<Trash2 className="size-5" aria-hidden />} onClick={() => void run("discard")}>
            {t("quote.form.discard")}
          </Button>
        )}
      </div>
    </section>
  );
}
