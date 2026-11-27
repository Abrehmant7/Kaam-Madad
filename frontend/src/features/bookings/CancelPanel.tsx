import { CalendarX } from "lucide-react";
import { useState } from "react";

import * as bookingsApi from "../../api/bookings";
import { Button } from "../../components/ui/Button";
import { IconTileGroup } from "../../components/ui/IconTile";
import { TextArea } from "../../components/ui/TextArea";
import { useI18n } from "../../i18n/context";
import { textDir } from "../jobs/text";

const REASONS: bookingsApi.CancelReason[] = ["not_available", "changed_plans", "no_show", "other"];

/** Cancel before the work starts (either person, with a reason). */
export function CancelPanel({ booking, act, busy }: {
  booking: bookingsApi.Booking; act: (action: () => Promise<bookingsApi.Booking>, options?: { showError?: boolean }) => Promise<boolean>; busy: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<bookingsApi.CancelReason[]>([]);
  const [note, setNote] = useState("");
  if (!booking.actions.cancel) return null;
  const ready = reason.length === 1 && (reason[0] !== "other" || note.trim().length >= 3);

  return (
    <details className="rounded-2xl border border-line bg-white p-3" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex min-h-11 cursor-pointer items-center gap-2 font-bold">
        <CalendarX className="size-5" aria-hidden />
        {t("cancel.title")}
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-sm">{t("cancel.intro")}</p>
        <IconTileGroup label={t("cancel.reasonLabel")} mode="single" columns={1} value={reason} onChange={setReason}
          options={REASONS.map((value) => ({ value, label: t(`cancel.reason.${value}`), icon: <CalendarX className="size-5" aria-hidden /> }))} />
        <TextArea label={t("cancel.noteLabel")} value={note} onChange={setNote} rows={2} maxLength={500} dir={note ? textDir(note) : "auto"} />
        <Button variant="danger" fullWidth loading={busy} loadingLabel={t("onboarding.saving")} disabled={!ready}
          onClick={() => void act(() => bookingsApi.cancelBooking(booking.id, reason[0]!, note.trim()))}>
          {t("cancel.confirm")}
        </Button>
      </div>
    </details>
  );
}
