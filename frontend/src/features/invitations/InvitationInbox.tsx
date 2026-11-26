import { Inbox } from "lucide-react";
import { Link } from "react-router";

import * as invitationsApi from "../../api/invitations";
import { Ltr } from "../../components/Ltr";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useI18n } from "../../i18n/context";
import { labeller, loadJobCatalog } from "../jobs/catalog";
import { formatDate, formatTime } from "../jobs/time";
import { LoadError, useLoad } from "../worker/shared";

/** Worker dashboard card: invitations addressed to the signed-in worker only. */
export function InvitationInbox() {
  const { t, language } = useI18n();
  const data = useLoad((signal) => Promise.all([invitationsApi.fetchInbox(signal), loadJobCatalog(signal)]));
  return (
    <section aria-labelledby="inbox-heading" className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
      <h2 id="inbox-heading" className="flex items-center gap-2 text-lg font-bold">
        <Inbox className="size-5" aria-hidden />
        {t("inv.inbox.heading")}
      </h2>
      {data.state.status === "loading" && <PageLoader />}
      {data.state.status === "error" && <LoadError error={data.state.error} onRetry={data.retry} />}
      {data.state.status === "ready" &&
        (() => {
          const [inbox, catalog] = data.state.data;
          const label = labeller(catalog, language);
          if (inbox.results.length === 0) return <p className="text-muted">{t("inv.inbox.empty")}</p>;
          return (
            <ul className="space-y-2">
              {inbox.results.map((item) => (
                <li key={item.id} className="space-y-1 rounded-xl border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={item.status === "active" ? "info" : "neutral"}>{t(`inv.status.${item.status}`)}</StatusBadge>
                    <span className="font-bold">
                      {label.trade(item.job.trade)}: {item.job.services.map(label.service).join(language === "ur" ? "، " : ", ")}
                    </span>
                  </div>
                  <p className="flex flex-wrap items-center gap-x-2 text-sm">
                    <span>{label.area(item.job.area)}</span>
                    <span>{formatDate(item.job.window_start, language)}</span>
                    <Ltr>{`${formatTime(item.job.window_start, language)} – ${formatTime(item.job.window_end, language)}`}</Ltr>
                  </p>
                  <Link to={`/worker/invitations/${item.id}`} className="inline-flex min-h-11 items-center font-bold text-primary underline-offset-4 hover:underline">
                    {t("jobs.list.open")}
                  </Link>
                </li>
              ))}
            </ul>
          );
        })()}
    </section>
  );
}
