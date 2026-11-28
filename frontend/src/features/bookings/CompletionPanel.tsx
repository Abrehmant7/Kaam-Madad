import { CircleCheck, Flag, Hourglass } from "lucide-react";
import { useState } from "react";

import * as bookingsApi from "../../api/bookings";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { TextArea } from "../../components/ui/TextArea";
import { isTranslationKey, useI18n } from "../../i18n/context";
import { textDir } from "../jobs/text";

type Act = (action: () => Promise<bookingsApi.Booking>, options?: { showError?: boolean }) => Promise<boolean>;
const REASONS: bookingsApi.DisputeReason[] = ["not_finished", "not_as_agreed", "damage", "price", "other"];

/** BK-06: the worker asks, the customer confirms or raises an issue; staff settle disputes. */
export function CompletionPanel({ booking, act, busy }: { booking: bookingsApi.Booking; act: Act; busy: boolean }) {
  const { t } = useI18n();
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState<bookingsApi.DisputeReason[]>([]);
  const [note, setNote] = useState("");
  const a = booking.actions;

  if (booking.status === "in_progress" && booking.role === "worker") {
    return (
      <section aria-labelledby="completion-heading" className="space-y-3 card-action p-4">
        <h2 id="completion-heading" className="text-lg font-bold">{t("completion.workerTitle")}</h2>
        <p className="text-sm">{t("completion.workerIntro")}</p>
        {a.completion_blocked_by_change && <Alert tone="warning">{t("completion.changeOpen")}</Alert>}
        <Button fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={!a.request_completion || a.completion_blocked_by_change}
          icon={<CircleCheck className="size-5" aria-hidden />} onClick={() => void act(() => bookingsApi.requestCompletion(booking.id))}>
          {t("completion.request")}
        </Button>
      </section>
    );
  }

  if (booking.status === "completion_requested") {
    if (booking.role === "worker") return <Alert tone="info" title={t("completion.waitingTitle")}>{t("completion.waitingBody")}</Alert>;
    const ready = reason.length === 1 && note.trim().length >= 3;
    return (
      <section aria-labelledby="confirm-heading" className="space-y-3 card-action p-4">
        <h2 id="confirm-heading" className="text-lg font-bold">{t("completion.customerTitle")}</h2>
        <p>{t("completion.customerIntro")}</p>
        <Button fullWidth loading={busy && !reporting} loadingLabel={t("onboarding.saving")} disabled={!a.confirm_completion || busy}
          icon={<CircleCheck className="size-5" aria-hidden />} onClick={() => void act(() => bookingsApi.confirmCompletion(booking.id))}>
          {t("completion.confirm")}
        </Button>
        {!reporting ? (
          <Button variant="secondary" fullWidth disabled={busy} icon={<Flag className="size-5" aria-hidden />} onClick={() => setReporting(true)}>
            {t("completion.raise")}
          </Button>
        ) : (
          <div className="space-y-3 rounded-xl border border-warning bg-warning-soft p-3">
            <p className="text-sm">{t("completion.raiseIntro")}</p>
            <IconTileGroup label={t("completion.reasonLabel")} mode="single" columns={1} value={reason} onChange={setReason}
              options={REASONS.map((value) => ({ value, label: t(`completion.reason.${value}`), icon: <Flag className="size-5" aria-hidden /> }))} />
            <TextArea label={t("completion.noteLabel")} value={note} onChange={setNote} rows={2} maxLength={500} dir={note ? textDir(note) : "auto"} />
            <Button variant="danger" fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={!ready}
              onClick={() => void act(() => bookingsApi.raiseIssue(booking.id, reason[0]!, note.trim()))}>
              {t("completion.raiseConfirm")}
            </Button>
            <Button variant="ghost" fullWidth onClick={() => setReporting(false)}>{t("accept.cancel")}</Button>
          </div>
        )}
      </section>
    );
  }

  if (booking.status === "disputed") {
    const reasonKey = booking.dispute_reason ? `completion.reason.${booking.dispute_reason}` : null;
    return (
      <Alert tone="warning" title={t("completion.disputedTitle")}>
        {reasonKey && isTranslationKey(reasonKey) && <p className="font-bold">{t(reasonKey)}</p>}
        {booking.dispute_note && <p dir={textDir(booking.dispute_note)}>“{booking.dispute_note}”</p>}
        <p className="mt-1 text-sm">{t(booking.role === "worker" ? "completion.disputedWorker" : "completion.disputedCustomer")}</p>
      </Alert>
    );
  }

  if (booking.status === "closed") {
    return (
      <Alert tone="info" title={t("completion.closedTitle")}>
        {booking.staff_reason && <p dir={textDir(booking.staff_reason)}>“{booking.staff_reason}”</p>}
        <p className="mt-1 text-sm">{t("completion.closedBody")}</p>
      </Alert>
    );
  }

  if (booking.status === "completed") {
    return (
      <Alert tone="success" title={t("completion.completedTitle")}>
        <p>{t("completion.completedBody")}</p>
      </Alert>
    );
  }

  if (booking.status === "in_progress" && booking.staff_outcome === "return_to_work") {
    return (
      <Alert tone="info" title={t("completion.returnedTitle")}>
        <p className="flex items-center gap-2"><Hourglass className="size-4" aria-hidden />{booking.staff_reason}</p>
      </Alert>
    );
  }
  return null;
}
