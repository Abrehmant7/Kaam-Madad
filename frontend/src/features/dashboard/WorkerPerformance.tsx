import { ChartNoAxesColumn, Star } from "lucide-react";
import type { ReactNode } from "react";

import * as workersApi from "../../api/workers";
import { Card } from "../../components/ui/PageHeader";
import { PageLoader } from "../../components/ui/PageLoader";
import { useI18n } from "../../i18n/context";
import { LoadError, useLoad } from "../worker/shared";

/** A thin horizontal bar: one hue on a quiet track, growing from the start side (right in Urdu, left in English). */
function Bar({ value, max }: { value: number; max: number }) {
  const width = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
  return (
    <span className="block h-2.5 w-full overflow-hidden rounded-full bg-[#eef1f7]" aria-hidden>
      <span className="block h-full rounded-full bg-primary" style={{ width: `${width}%` }} />
    </span>
  );
}

/** "1,234" in the Latin face inside Urdu text (exact counts, never rounded). */
function Count({ value }: { value: number }) {
  return <bdi dir="ltr" className="font-sans font-bold tabular-nums">{value.toLocaleString("en-PK")}</bdi>;
}

/**
 * Worker dashboard: Performance. Two small visuals from server totals (GET /workers/me/stats/):
 * - ratings: visible reviews per star (5 → 1) with the actual average and review count, or "No reviews yet";
 * - work: every invitation received (any status) beside customer-confirmed completed jobs.
 * Each bar has its exact count next to it, so nothing depends on reading a bar length or a colour.
 */
export function WorkerPerformance() {
  const { t } = useI18n();
  const data = useLoad((signal) => workersApi.fetchStats(signal));
  const card = (body: ReactNode) => (
    <Card id="performance" title={t("perf.heading")} icon={<ChartNoAxesColumn className="size-5" aria-hidden />}>{body}</Card>
  );
  if (data.state.status === "loading") return card(<PageLoader />);
  if (data.state.status === "error") return card(<LoadError error={data.state.error} onRetry={data.retry} />);
  const stats = data.state.data;
  const most = Math.max(...stats.rating_distribution.map((row) => row.count), 0);
  const workMax = Math.max(stats.invitations_received, stats.completed_jobs, 0);

  return card(
    <div className="space-y-5">
      <section aria-labelledby="perf-ratings" className="space-y-2">
        <h3 id="perf-ratings" className="text-sm font-bold text-muted">{t("perf.ratings")}</h3>
        {stats.review_count === 0 || stats.average_rating === null ? (
          <p className="text-sm text-muted">{t("rec.noReviews")}</p>
        ) : (
          <>
            <p className="flex flex-wrap items-baseline gap-x-2">
              <bdi dir="ltr" className="font-sans text-3xl font-bold">{stats.average_rating}</bdi>
              <span className="text-sm text-muted">{t("perf.outOfFive")}</span>
              <span className="text-sm">{t("feedback.reviewCount", { count: stats.review_count })}</span>
            </p>
            <ul className="space-y-1.5" aria-label={t("perf.distribution")}>
              {stats.rating_distribution.map((row) => (
                <li key={row.stars} className="grid grid-cols-[3.25rem_minmax(0,1fr)_2.5rem] items-center gap-2 text-sm">
                  <span className="flex items-center gap-1" aria-label={t("perf.stars", { count: row.stars })}>
                    <bdi dir="ltr" className="font-sans">{row.stars}</bdi>
                    <Star className="size-4 fill-accent text-warning-strong" aria-hidden />
                  </span>
                  <Bar value={row.count} max={most} />
                  <span className="text-end"><Count value={row.count} /></span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="perf-work" className="space-y-2">
        <h3 id="perf-work" className="text-sm font-bold text-muted">{t("perf.work")}</h3>
        <dl className="space-y-2.5">
          {([["perf.invitations", stats.invitations_received], ["perf.completed", stats.completed_jobs]] as const).map(([key, value]) => (
            <div key={key} className="space-y-1">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <dt>{t(key)}</dt>
                <dd><Count value={value} /></dd>
              </div>
              <Bar value={value} max={workMax} />
            </div>
          ))}
        </dl>
        <p className="text-xs text-muted">{t("perf.note")}</p>
      </section>
    </div>,
  );
}
