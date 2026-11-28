import { Check, FilePen, Undo2, X } from "lucide-react";
import { useState } from "react";

import * as bookingsApi from "../../api/bookings";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { TextArea } from "../../components/ui/TextArea";
import { useI18n } from "../../i18n/context";
import { fieldErrorCodes, fieldErrorText } from "../../i18n/errors";
import { labourText, materialsText, money, visitText, windowText } from "../conversations/quoteText";
import { TermsFields, useTerms } from "../conversations/TermsFields";
import { textDir } from "../jobs/text";

type Act = (action: () => Promise<bookingsApi.Booking>, options?: { showError?: boolean }) => Promise<boolean>;
type T = ReturnType<typeof useI18n>["t"];

function describe(terms: bookingsApi.BookingTerms, t: T, language: "ur" | "en") {
  const when = windowText(terms, language);
  return {
    scope: terms.scope,
    quantity: terms.quantity == null ? "—" : String(terms.quantity),
    labour: labourText(terms, t),
    materials: materialsText(terms, t),
    visit: visitText(terms, t),
    exclusions: terms.exclusions || "—",
    when: when ? `${when.date} ${when.time}` : "—",
    total: `${money(terms.totals?.known_total) ?? ""}${terms.totals && !terms.totals.complete ? ` ${t("quote.plusUnknown")}` : ""}`,
  };
}

const ROWS = [
  ["scope", "quote.field.scope"], ["quantity", "quote.field.quantity"], ["labour", "quote.field.labour"],
  ["materials", "quote.field.materials"], ["visit", "quote.field.visit"], ["exclusions", "quote.field.exclusions"],
  ["when", "quote.field.when"], ["total", "quote.field.total"],
] as const;

/** Old and proposed terms side by side: only what changes. */
function ChangeDiff({ change }: { change: bookingsApi.BookingChange }) {
  const { t, language } = useI18n();
  const before = describe(change.old_terms, t, language);
  const after = describe(change.new_terms, t, language);
  // Free text follows its own script; generated lines ("فی عدد PKR 600 × 2 …") follow the UI language.
  const dirOf = (key: string, value: string) => (key === "scope" || key === "exclusions" ? textDir(value) : language === "ur" ? "rtl" : "ltr");
  return (
    <dl className="space-y-2">
      {ROWS.filter(([key]) => before[key] !== after[key]).map(([key, title]) => (
        <div key={key} className="rounded-lg bg-white p-2">
          <dt className="text-sm font-bold">{t(title)}</dt>
          <dd className="text-sm">
            <span className="text-muted">{t("change.before")}: </span><bdi dir={dirOf(key, before[key])} className="line-through">{before[key]}</bdi>
          </dd>
          <dd className="text-sm font-bold">
            <span className="font-normal text-muted">{t("change.after")}: </span><bdi dir={dirOf(key, after[key])}>{after[key]}</bdi>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ProposeForm({ booking, act, busy, onClose }: { booking: bookingsApi.Booking; act: Act; busy: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const state = useTerms(booking.terms);
  const [note, setNote] = useState("");
  const [codes, setCodes] = useState<Record<string, string[]>>({});
  const errors = (name: string) => (codes[name] ?? []).map((code) => fieldErrorText(code, t));

  async function send() {
    setCodes({});
    const ok = await act(async () => {
      try {
        return await bookingsApi.proposeChange(booking.id, state.terms(), note.trim());
      } catch (error) {
        setCodes(fieldErrorCodes(error));
        throw error;
      }
    });
    if (ok) onClose();
  }

  return (
    <section aria-labelledby="propose-heading" className="space-y-4 card-action p-4">
      <h3 id="propose-heading" className="text-lg font-bold">{t("change.formTitle")}</h3>
      <p className="text-sm text-muted">{t("change.formIntro")}</p>
      <TermsFields state={state} errors={errors} allowTime={booking.actions.change_time} />
      <TextArea label={t("change.noteLabel")} hint={t("change.noteHint")} value={note} onChange={setNote} errors={errors("note")} rows={2}
        maxLength={500} dir={note ? textDir(note) : "auto"} />
      {(codes.non_field_errors ?? []).includes("no_change") && <Alert tone="warning">{t("change.noChange")}</Alert>}
      <div className="grid gap-2">
        <Button fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={note.trim().length < 3} onClick={() => void send()}>
          {t("change.send")}
        </Button>
        <Button variant="ghost" onClick={onClose}>{t("accept.cancel")}</Button>
      </div>
    </section>
  );
}

/** QT-04: proposals need the other person's approval; the agreement in effect stays until then. */
export function ChangesPanel({ booking, act, busy }: { booking: bookingsApi.Booking; act: Act; busy: boolean }) {
  const { t } = useI18n();
  const [proposing, setProposing] = useState(false);
  const pending = booking.changes.find((change) => change.status === "pending");
  const past = booking.changes.filter((change) => change.status !== "pending");

  return (
    <section aria-labelledby="changes-heading" className="space-y-3">
      <h2 id="changes-heading" className="flex items-center gap-2 text-lg font-bold">
        <FilePen className="size-5" aria-hidden />
        {t("change.title")}
      </h2>
      {pending && (
        <div className="space-y-2 rounded-2xl border-2 border-warning bg-warning-soft p-3">
          <StatusBadge tone="warning">{t("change.pending", { number: pending.number })}</StatusBadge>
          <p className="text-sm">
            {pending.can_approve ? t("change.waitingForYou", { role: t(`conv.role.${pending.proposed_role}`) }) : t("change.waitingForOther")}
          </p>
          {pending.note && <p className="text-sm" dir={textDir(pending.note)}>“{pending.note}”</p>}
          <ChangeDiff change={pending} />
          <p className="text-xs text-muted">{t("change.stillInEffect")}</p>
          {pending.can_approve && (
            <div className="grid grid-cols-2 gap-2">
              <Button loading={busy} loadingLabel={t("onboarding.saving")} icon={<Check className="size-5" aria-hidden />}
                onClick={() => void act(() => bookingsApi.decideChange(booking.id, pending.id, "approve"))}>
                {t("change.approve")}
              </Button>
              <Button variant="secondary" disabled={busy} icon={<X className="size-5" aria-hidden />}
                onClick={() => void act(() => bookingsApi.decideChange(booking.id, pending.id, "reject"))}>
                {t("change.reject")}
              </Button>
            </div>
          )}
          {pending.can_withdraw && (
            <Button variant="ghost" disabled={busy} icon={<Undo2 className="size-5" aria-hidden />}
              onClick={() => void act(() => bookingsApi.decideChange(booking.id, pending.id, "withdraw"))}>
              {t("change.withdraw")}
            </Button>
          )}
        </div>
      )}
      {booking.actions.propose_change && !proposing && (
        <Button variant="secondary" fullWidth icon={<FilePen className="size-5" aria-hidden />} onClick={() => setProposing(true)}>
          {t("change.propose")}
        </Button>
      )}
      {proposing && booking.actions.propose_change && (
        <ProposeForm booking={booking} act={act} busy={busy} onClose={() => setProposing(false)} />
      )}
      {past.length > 0 && (
        <ul className="space-y-2">
          {past.map((change) => (
            <li key={change.id} className="space-y-1 rounded-xl border border-line bg-white p-3 text-sm">
              <StatusBadge tone={change.status === "approved" ? "success" : "neutral"}>
                {t("change.number", { number: change.number })} · {t(`change.status.${change.status}`)}
              </StatusBadge>
              {change.note && <p dir={textDir(change.note)}>“{change.note}”</p>}
              <ChangeDiff change={change} />
            </li>
          ))}
        </ul>
      )}
      {!pending && past.length === 0 && !booking.actions.propose_change && <p className="text-sm text-muted">{t("change.none")}</p>}
    </section>
  );
}
