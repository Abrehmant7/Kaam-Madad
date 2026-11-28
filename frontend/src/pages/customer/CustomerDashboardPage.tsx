import { ClipboardList, Flag, House, List, MessageSquarePlus, Phone, ShieldCheck } from "lucide-react";
import type { CSSProperties } from "react";
import { Link } from "react-router";

import * as jobsApi from "../../api/jobs";
import heroImage from "../../assets/hero-electrician.webp";
import { useAuth } from "../../auth/context";
import { PATHS } from "../../auth/paths";
import { Ltr } from "../../components/Ltr";
import { ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/PageHeader";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { BookingList } from "../../features/bookings/BookingList";
import { CustomerNextStep } from "../../features/dashboard/NextStep";
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
    <li className="space-y-2 rounded-xl border border-line bg-[#fbfcff] p-3">
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

/** Customer dashboard: the next relevant step, "Describe your job", My requests (#requests), My bookings (#bookings). */
export function CustomerDashboardPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const data = useLoad((signal) => Promise.all([jobsApi.listJobs(signal), loadJobCatalog(signal)]));
  if (!user) return null;
  const jobs = data.state.status === "ready" ? data.state.data[0].results : null;

  return (
    <div className="space-y-5">
      <section aria-labelledby="customer-title" className="hero on-dark flex min-h-[12rem] items-center px-5 py-6 sm:min-h-[14rem] sm:px-8"
        style={{ "--hero-image": `url(${heroImage})` } as CSSProperties}>
        <div className="relative max-w-[68%] space-y-2 sm:max-w-[60%]">
          <h1 id="customer-title" className="font-display text-2xl text-white sm:text-3xl">{t("home.customer.title")}</h1>
          <p className="text-sm text-[#dee7ff]">{t("home.customer.subtitle")}</p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/30 bg-white/10 px-3 py-0.5 text-sm font-bold">
              <House className="size-4" aria-hidden />
              {t("role.customer.badge")}
            </span>
            {user.is_demo && <StatusBadge tone="warning">{t("demo.accountBadge")}</StatusBadge>}
          </div>
          <p className="flex flex-wrap items-center gap-1.5 text-sm text-[#dee7ff]">
            <span>{t("home.signedInAs")}</span>
            <Ltr>{user.phone_number_masked}</Ltr>
          </p>
          <ButtonLink to={PATHS.newJob} variant="gold" icon={<MessageSquarePlus className="size-5" aria-hidden />}>
            {t("jobs.describe.cta")}
          </ButtonLink>
        </div>
      </section>

      <AccountNotices />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.75fr)_minmax(17rem,1fr)]">
        <div className="space-y-5">
          {data.state.status !== "loading" && <CustomerNextStep jobs={jobs} />}
          <Card id="requests" title={t("jobs.list.heading")} icon={<ClipboardList className="size-5" aria-hidden />}
            action={<Link to={PATHS.newJob} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-bold text-primary hover:underline">
              <MessageSquarePlus className="size-4" aria-hidden />{t("nav.newRequest")}</Link>}>
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
          </Card>
          <BookingList />
        </div>

        <div className="space-y-5">
          <Card id="phone" title={t("home.phoneStatus")} icon={<Phone className="size-5" aria-hidden />}>
            <PhoneConfirmationBadge confirmation={user.phone_confirmation} />
            <div>
              <ButtonLink to={PATHS.phone} variant="secondary" icon={<ShieldCheck className="size-5" aria-hidden />}>
                {t("home.managePhone")}
              </ButtonLink>
            </div>
          </Card>
          <Card title={t("nav.reports")} icon={<Flag className="size-5" aria-hidden />}>
            <p className="text-sm text-muted">{t("home.reportsNote")}</p>
            <ButtonLink to="/reports" variant="secondary" icon={<Flag className="size-5" aria-hidden />}>{t("home.openReports")}</ButtonLink>
          </Card>
          <Link to={PATHS.catalog} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
            <List className="size-5" aria-hidden />
            {t("landing.catalogLink")}
          </Link>
        </div>
      </div>
    </div>
  );
}
