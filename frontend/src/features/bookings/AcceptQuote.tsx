import { CalendarCheck, CircleCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import * as bookingsApi from "../../api/bookings";
import { ApiError, ConnectionError } from "../../api/client";
import * as convApi from "../../api/conversations";
import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";
import { money, windowText } from "../conversations/quoteText";
import { isolateLtr } from "../jobs/text";

type Phase = "closed" | "review" | "sending" | "checking" | "unconfirmed";

/** Customer: review the exact version and accept it (BK-01, BK-03). */
export function AcceptQuote({ invitationId, quote, onStale }: { invitationId: string; quote: convApi.Quote; onStale: () => void }) {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>("closed");
  const [failure, setFailure] = useState<unknown>(null);
  const when = windowText(quote, language);
  const totals = quote.totals;
  const unknown = totals?.unknown ?? [];
  // Each amount is an LTR island so "PKR 1,200" never reorders inside Urdu text.
  const amount = (value: string | null | undefined) => { const shown = money(value); return shown ? isolateLtr(shown) : t("quote.unknown"); };

  function done(bookingId: string) {
    bookingsApi.forgetAcceptanceKey(quote.id);
    navigate(`/bookings/${bookingId}`);
  }

  async function accept() {
    setFailure(null);
    setPhase("sending");
    const key = bookingsApi.acceptanceKey(quote.id); // the same key for every retry of this version
    try {
      const booking = await bookingsApi.acceptQuote({ invitation_id: invitationId, quote_id: quote.id, version: quote.version ?? 0, idempotency_key: key });
      done(booking.id);
    } catch (error) {
      if (error instanceof ConnectionError) {
        // The result is unknown: ask the server before offering "accept" again (SEC-05).
        setPhase("checking");
        try {
          const header = await convApi.fetchConversation(invitationId);
          if (header.booking && header.booking.status !== "cancelled") {
            done(header.booking.id);
            return;
          }
          setPhase("unconfirmed");
        } catch {
          setPhase("unconfirmed");
        }
        return;
      }
      setFailure(error);
      setPhase("review");
      if (error instanceof ApiError && ["quote_not_current", "quote_expired", "quote_not_ready"].includes(error.code)) onStale();
    }
  }

  const bookedId = failure instanceof ApiError && typeof failure.details.booking_id === "string" ? failure.details.booking_id : null;

  if (phase === "closed") {
    return (
      <Button fullWidth icon={<CalendarCheck className="size-5" aria-hidden />} onClick={() => setPhase("review")}>
        {t("accept.open")}
      </Button>
    );
  }

  return (
    <section aria-labelledby="accept-heading" className="space-y-3 card-action p-4">
      <h3 id="accept-heading" className="text-lg font-bold">{t("accept.title", { version: quote.version ?? "" })}</h3>
      <dl className="space-y-2">
        <div>
          <dt className="text-sm text-muted">{t("accept.time")}</dt>
          <dd className="font-bold">
            {when ? <span className="flex flex-col"><span>{when.date}</span><Ltr className="self-start">{when.time}</Ltr></span> : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-muted">{t("accept.known")}</dt>
          <dd className="font-bold">
            <Ltr>{money(totals?.known_total) ?? "—"}</Ltr>
            <span className="block text-sm font-normal text-muted">
              {t("accept.breakdown", { labour: amount(totals?.labour_total), materials: amount(totals?.materials_total), visit: amount(totals?.visit_total) })}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-sm text-muted">{t("accept.unknown")}</dt>
          <dd className="font-bold">
            {unknown.length === 0 ? t("accept.nothingUnknown") : unknown.map((part) => t(`accept.unknownPart.${part}` as never)).join(language === "ur" ? "، " : ", ")}
          </dd>
        </div>
      </dl>
      <Alert tone="info" title={t("accept.nextTitle")}>
        <ul className="list-inside list-disc space-y-1">
          <li>{t("accept.next.reserve")}</li>
          <li>{t("accept.next.address")}</li>
          <li>{t("accept.next.cancel")}</li>
          <li>{t("accept.next.code")}</li>
        </ul>
      </Alert>
      <p className="text-sm text-muted">{t("accept.limits")}</p>

      {phase === "checking" && <Alert tone="info">{t("accept.checking")}</Alert>}
      {phase === "unconfirmed" && <Alert tone="warning" title={t("accept.unconfirmedTitle")}>{t("accept.unconfirmedBody")}</Alert>}
      {failure !== null && (
        <Alert tone="danger">
          <p>{describeError(failure, t)}</p>
          {bookedId && (
            <ButtonLink to={`/bookings/${bookedId}`} variant="secondary" className="mt-2">{t("booking.open")}</ButtonLink>
          )}
        </Alert>
      )}
      <div className="grid gap-2">
        <Button fullWidth loading={phase === "sending" || phase === "checking"} loadingLabel={t("accept.sending")}
          icon={<CircleCheck className="size-5" aria-hidden />} onClick={() => void accept()}>
          {phase === "unconfirmed" ? t("accept.retry") : t("accept.confirm")}
        </Button>
        <Button variant="ghost" disabled={phase === "sending" || phase === "checking"} onClick={() => { setPhase("closed"); setFailure(null); }}>
          {t("accept.cancel")}
        </Button>
      </div>
    </section>
  );
}
