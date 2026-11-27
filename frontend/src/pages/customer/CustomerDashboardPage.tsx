import { ClipboardList, House, List, MessageSquarePlus, Phone, ShieldCheck } from "lucide-react";
import { Link } from "react-router";

import * as jobsApi from "../../api/jobs";
import { useAuth } from "../../auth/context";
import { PATHS } from "../../auth/paths";
import { Ltr } from "../../components/Ltr";
import { ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { BookingList } from "../../features/bookings/BookingList";
import { AccountNotices } from "../../features/reports/AccountNotices";
import { type JobCatalog, labeller, loadJobCatalog } from "../../features/jobs/catalog";
import { textDir } from "../../features/jobs/text";
import { formatDate, formatTime } from "../../features/jobs/time";
import { PhoneConfirmationBadge } from "../../features/phone/PhoneConfirmationStatus";
import { LoadError, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";

function RequestCard({ job, catalog }: { job: jobsApi.JobListItem; catalog: JobCatalog }) {
  const { t, language } = useI18n();
  const label = labeller(catalog, language);
  const draft = job.status === "draft";
  const task = job.trade ? `${label.trade(job.trade)}${job.services.length ? `: ${job.services.map(label.service).join(language === "ur" ? "، " : ", ")}` : ""}` : t("jobs.list.untitled");
  return (
    <li className="space-y-2 rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={draft ? "neutral" : "success"}>{draft ? t("jobs.status.draft") : t("jobs.status.confirmed")}</StatusBadge>
        {job.booking && <StatusBadge tone="info">{t(`booking.status.${job.booking.status}`)}</StatusBadge>}
        <span className="font-bold">{task}</span>
      </div>
      {job.description && <p dir={textDir(job.description)} className="line-clamp-2 text-sm text-muted">{job.description}</p>}
      <p className="flex flex-wrap items-center gap-x-2 text-sm">
        <span>{job.area ? `${label.area(job.area)}${language === "ur" ? "، " : ", "}${label.city(job.city)}` : t("jobs.list.noArea")}</span>
        {job.window_start && job.window_end && (
          <>
            <span>{formatDate(job.window_start, language)}</span>
            <Ltr>{`${formatTime(job.window_start, language)} – ${formatTime(job.window_end, language)}`}</Ltr>
          </>
        )}
      </p>
      <Link
        to={draft ? `/customer/requests/${job.id}/details` : `/customer/requests/${job.id}`}
        className="inline-flex min-h-11 items-center font-bold text-primary underline-offset-4 hover:underline"
      >
        {draft ? t("jobs.list.continue") : t("jobs.list.open")}
      </Link>
    </li>
  );
}

/** Customer dashboard (M5): describe a job, see "My requests", confirm the phone. */
export function CustomerDashboardPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const data = useLoad((signal) => Promise.all([jobsApi.listJobs(signal), loadJobCatalog(signal)]));
  if (!user) return null;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-primary">{t("home.customer.title")}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="info" icon={<House className="size-4" aria-hidden />}>{t("role.customer.badge")}</StatusBadge>
          {user.is_demo && <StatusBadge tone="warning">{t("demo.accountBadge")}</StatusBadge>}
        </div>
        <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
          <span>{t("home.signedInAs")}</span>
          <Ltr>{user.phone_number_masked}</Ltr>
        </p>
      </div>

      <ButtonLink to={PATHS.newJob} fullWidth icon={<MessageSquarePlus className="size-5" aria-hidden />}>
        {t("jobs.describe.cta")}
      </ButtonLink>

      <AccountNotices />
      <BookingList />

      <section aria-labelledby="requests-heading" className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
        <h2 id="requests-heading" className="flex items-center gap-2 text-lg font-bold">
          <ClipboardList className="size-5" aria-hidden />
          {t("jobs.list.heading")}
        </h2>
        {data.state.status === "loading" && <PageLoader />}
        {data.state.status === "error" && <LoadError error={data.state.error} onRetry={data.retry} />}
        {data.state.status === "ready" &&
          (data.state.data[0].results.length === 0 ? (
            <p className="text-muted">{t("jobs.list.empty")}</p>
          ) : (
            <ul className="space-y-2">
              {data.state.data[0].results.map((job) => (
                <RequestCard key={job.id} job={job} catalog={data.state.status === "ready" ? data.state.data[1] : { trades: [], services: [], areas: [] }} />
              ))}
            </ul>
          ))}
      </section>

      <section aria-labelledby="phone-heading" className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
        <h2 id="phone-heading" className="flex items-center gap-2 text-lg font-bold">
          <Phone className="size-5" aria-hidden />
          {t("home.phoneStatus")}
        </h2>
        <PhoneConfirmationBadge confirmation={user.phone_confirmation} />
        <div>
          <ButtonLink to={PATHS.phone} variant="secondary" icon={<ShieldCheck className="size-5" aria-hidden />}>
            {t("home.managePhone")}
          </ButtonLink>
        </div>
      </section>

      <section aria-labelledby="next-heading" className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
        <h2 id="next-heading" className="text-lg font-bold">{t("home.nextHeading")}</h2>
        <ul className="space-y-2">
          {(["home.customer.next.recommend", "home.customer.next.chat"] as const).map((key) => (
            <li key={key} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2">
              <span>{t(key)}</span>
              <StatusBadge tone="neutral">{t("common.notAvailableYet")}</StatusBadge>
            </li>
          ))}
        </ul>
      </section>

      <Link to={PATHS.catalog} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
        <List className="size-5" aria-hidden />
        {t("landing.catalogLink")}
      </Link>
    </div>
  );
}
