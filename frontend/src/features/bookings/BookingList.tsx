import { CalendarCheck } from "lucide-react";

import * as bookingsApi from "../../api/bookings";
import { workerRef } from "../../api/invitations";
import { Ltr } from "../../components/Ltr";
import { ButtonLink } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useI18n } from "../../i18n/context";
import { labeller, loadJobCatalog } from "../jobs/catalog";
import { formatDate, formatTime } from "../jobs/time";
import { LoadError, useLoad } from "../worker/shared";
import { money } from "../conversations/quoteText";

export const STATUS_TONE = { confirmed: "info", arrived: "warning", in_progress: "success", cancelled: "neutral" } as const;

/** "My bookings" on both dashboards. Renders nothing until there is at least one booking. */
export function BookingList() {
  const { t, language } = useI18n();
  const data = useLoad((signal) => Promise.all([bookingsApi.listBookings(signal), loadJobCatalog(signal)]), []);
  if (data.state.status === "loading") return null;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [page, catalog] = data.state.data;
  if (page.results.length === 0) return null;
  const label = labeller(catalog, language);

  return (
    <section aria-labelledby="bookings-heading" className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
      <h2 id="bookings-heading" className="flex items-center gap-2 text-lg font-bold">
        <CalendarCheck className="size-6 text-primary" aria-hidden />
        {t("booking.list.heading")}
      </h2>
      <ul className="space-y-3">
        {page.results.map((card) => (
          <li key={card.id} className="space-y-2 rounded-xl border border-line p-3">
            <StatusBadge tone={STATUS_TONE[card.status]}>{t(`booking.status.${card.status}`)}</StatusBadge>
            <p className="font-bold">
              {label.trade(card.trade)}: {card.services.map((code) => label.service(code)).join(language === "ur" ? "، " : ", ")}
            </p>
            <p className="text-sm">
              {label.area(card.area)} · {formatDate(card.start_at, language)}{" "}
              <Ltr>{`${formatTime(card.start_at, language)} – ${formatTime(card.end_at, language)}`}</Ltr>
            </p>
            {card.known_total && (
              <p className="text-sm">
                {t("quote.field.total")}: <Ltr>{money(card.known_total) ?? ""}</Ltr>
                {!card.complete && ` ${t("quote.plusUnknown")}`}
              </p>
            )}
            {card.worker_id && <p className="text-sm text-muted">{t("rec.ref")} {workerRef(card.worker_id)}</p>}
            <ButtonLink to={`/bookings/${card.id}`} variant="secondary">{t("booking.open")}</ButtonLink>
          </li>
        ))}
      </ul>
    </section>
  );
}
