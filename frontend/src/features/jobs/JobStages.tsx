import { Check } from "lucide-react";
import { Link } from "react-router";

import type { BookingStatus } from "../../api/bookings";
import type { QuotesListing } from "../../api/conversations";
import { useI18n } from "../../i18n/context";

export type JobStage = "chat" | "quote" | "work";

export const stagePath = {
  chat: (invitationId: string) => `/conversations/${invitationId}`,
  quote: (invitationId: string, edit = false) => `/conversations/${invitationId}/quote${edit ? "?edit=1" : ""}`,
  work: (bookingId: string) => `/bookings/${bookingId}`,
};

/** What the server says about the job, as far as this screen knows it. `quote: undefined` = still loading. */
export interface StageFacts {
  invitationId: string;
  role: "customer" | "worker";
  /** Whether messages can still be sent; unknown on the booking screen (no status shown then). */
  chatOpen?: boolean;
  quote?: Pick<QuotesListing, "current" | "draft" | "readiness"> | null;
  /** The accepted version, when the screen only knows the booking. */
  acceptedVersion?: number | null;
  booking: { id: string; status: BookingStatus | null } | null;
}

/** How far the job has got: a booking means work, a sent quote means the quote stage, otherwise request & chat. */
export function reachedStage(facts: StageFacts): JobStage {
  if (facts.booking) return "work";
  if (facts.quote?.current) return "quote";
  return "chat";
}

const ORDER: JobStage[] = ["chat", "quote", "work"];

/**
 * Request & chat → Quote → Work progress. The same three steps for both roles, built from the invitation, its quotes
 * and its booking. Each step says where it stands and links to its own screen, so nobody has to walk through earlier
 * screens to reach the current one. Work progress is a link only once a booking exists.
 */
export function JobStages({ facts, current }: { facts: StageFacts; current: JobStage }) {
  const { t } = useI18n();
  const reached = ORDER.indexOf(reachedStage(facts));
  const { quote, booking } = facts;

  const status: Record<JobStage, string> = {
    chat: facts.chatOpen === undefined ? "" : facts.chatOpen ? t("stage.chat.open") : t("stage.chat.closed"),
    quote: (() => {
      if (booking && booking.status !== "cancelled") {
        const version = facts.acceptedVersion ?? quote?.readiness.version ?? quote?.current?.version;
        return version ? t("stage.quote.accepted", { version }) : t("stage.quote.acceptedPlain");
      }
      if (quote === undefined) return "";
      if (quote?.current) {
        const version = quote.current.version ?? "";
        return quote.readiness.ready ? t("stage.quote.ready", { version }) : t("stage.quote.blocked", { version });
      }
      if (quote?.draft && facts.role === "worker") return t("stage.quote.draft");
      return t("stage.quote.none");
    })(),
    work: booking ? (booking.status ? t(`booking.status.${booking.status}`) : t("booking.status.confirmed")) : t("stage.work.none"),
  };
  const href: Record<JobStage, string | null> = {
    chat: stagePath.chat(facts.invitationId),
    quote: stagePath.quote(facts.invitationId),
    work: booking ? stagePath.work(booking.id) : null,
  };

  return (
    <nav aria-label={t("stage.label")}>
      <ol className="grid grid-cols-3 gap-2 sm:gap-3">
        {ORDER.map((stage, index) => {
          const done = index < reached;
          const here = stage === current;
          const tone = here ? "border-primary text-primary" : done || index <= reached ? "border-primary/40 text-ink" : "border-line text-muted";
          const body = (
            <>
              <span className="flex items-center gap-1.5 text-xs font-bold leading-tight sm:text-sm">
                <span className={`inline-grid size-5 shrink-0 place-items-center rounded-full font-sans text-[11px] ${
                  here ? "bg-primary text-white" : done ? "bg-primary-soft text-primary" : "bg-[#eef1f7] text-muted"}`} aria-hidden>
                  {done && !here ? <Check className="size-3.5" /> : index + 1}
                </span>
                <span className="min-w-0">{t(`stage.${stage}`)}</span>
              </span>
              {status[stage] && <span className="mt-0.5 block truncate text-xs text-muted">{status[stage]}</span>}
            </>
          );
          const target = href[stage];
          return (
            <li key={stage} className={`min-w-0 border-t-4 pt-1.5 ${tone}`}>
              {target && !here ? (
                <Link to={target} className="block min-h-11 rounded-md hover:text-primary focus-visible:outline-offset-2">{body}</Link>
              ) : (
                <span className="block min-h-11" aria-current={here ? "step" : undefined}>{body}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
