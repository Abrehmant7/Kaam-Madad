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

export const STATUS_TONE = {
  confirmed: "info", arrived: "warning", in_progress: "success", completion_requested: "warning", completed: "success",
  disputed: "danger", closed: "neutral", cancelled: "neutral",
} as const;

/** Dashboard groups (both roles): what needs attention first. */
const GROUPS: { key: string; statuses: bookingsApi.BookingStatus[] }[] = [
  { key: "awaiting", statuses: ["completion_requested"] },
  { key: "disputed", statuses: ["disputed"] },
  { key: "active", statuses: ["confirmed", "arrived", "in_progress"] },
  { key: "completed", statuses: ["completed"] },
  { key: "past", statuses: ["closed", "cancelled"] },
];

function nextStep(card: bookingsApi.BookingCard): string | null {
  if (card.role === "customer") {
    if (card.status === "completion_requested") return "booking.next.customerConfirm";
    if (card.status === "completed" && !card.review_submitted) return "booking.next.customerReview";
    if (card.status === "arrived") return "booking.next.customerCode";
  } else {
    if (card.status === "completion_requested") return "booking.next.workerWaiting";
    if (card.status === "in_progress") return "booking.next.workerFinish";
    if (card.status === "confirmed") return "booking.next.workerArrive";
  }
  if (card.status === "disputed") return "booking.next.disputed";
  return null;
}

/** "My bookings" on both dashboards, grouped by stage. Renders nothing until there is at least one booking. */
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
      {GROUPS.map((group) => {
        const cards = page.results.filter((card) => group.statuses.includes(card.status));
        if (cards.length === 0) return null;
        return (
          <div key={group.key} className="space-y-2">
            <h3 className="font-bold text-muted">{t(`booking.group.${group.key}` as never)} ({cards.length})</h3>
            <ul className="space-y-3">
              {cards.map((card) => {
                const next = nextStep(card);
                return (
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
                    {next && <p className="text-sm font-bold text-primary">{t(next as never)}</p>}
                    <ButtonLink to={`/bookings/${card.id}`} variant={next ? "primary" : "secondary"}>{t("booking.open")}</ButtonLink>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
