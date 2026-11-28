import { CirclePause, CirclePlay, HardHat, List, ShieldAlert, UserRoundPen } from "lucide-react";
import { type CSSProperties, useState } from "react";
import { Link, Navigate, useLocation } from "react-router";

import heroImage from "../../assets/hero-electrician.webp";
import * as workersApi from "../../api/workers";
import { useAuth } from "../../auth/context";
import { PATHS } from "../../auth/paths";
import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/PageHeader";
import { PageLoader } from "../../components/ui/PageLoader";
import { BookingList } from "../../features/bookings/BookingList";
import { WorkerFeedback } from "../../features/bookings/WorkerFeedback";
import { WorkerNextStep } from "../../features/dashboard/NextStep";
import { WorkerPerformance } from "../../features/dashboard/WorkerPerformance";
import { InvitationInbox } from "../../features/invitations/InvitationInbox";
import { AccountNotices } from "../../features/reports/AccountNotices";
import { LoadError, onboardingPath, useLoad } from "../../features/worker/shared";
import { isTranslationKey, useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";

/** Old dashboard section links that moved to their own pages. */
const MOVED: Record<string, string> = { "#profile": PATHS.workerProfile, "#identity": PATHS.workerVerify, "#phone": PATHS.phone };
const IDENTITY_REASONS = new Set(["identity_not_started", "identity_not_verified", "identity_no_match", "identity_rejected",
  "identity_expired", "identity_suspended", "demo_approval_not_accepted_here"]);

/** Receive new job requests: the worker's own on/off choice, as a main card beside invitations and bookings. */
function ReceivingCard({ accepting, onToggle }: { accepting: boolean; onToggle: () => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  async function toggle() {
    setFailure(null);
    setBusy(true);
    try {
      await onToggle();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }
  const Icon = accepting ? CirclePlay : CirclePause;
  return (
    <Card id="accepting" title={t("worker.accepting.label")} icon={<Icon className="size-5" aria-hidden />}>
      <p role="status" className={`flex items-center gap-2 text-lg font-bold ${accepting ? "text-success-strong" : "text-warning-strong"}`}>
        <Icon className="size-6 shrink-0" aria-hidden />
        {accepting ? t("worker.accepting.onLong") : t("worker.accepting.offLong")}
      </p>
      <p className="text-sm text-muted">{t("worker.accepting.help")}</p>
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      <Button variant={accepting ? "secondary" : "primary"} loading={busy} loadingLabel={t("onboarding.saving")}
        icon={accepting ? <CirclePause className="size-5" aria-hidden /> : <CirclePlay className="size-5" aria-hidden />}
        onClick={() => void toggle()}>
        {accepting ? t("worker.accepting.turnOff") : t("worker.accepting.turnOn")}
      </Button>
    </Card>
  );
}

/**
 * Worker dashboard: the next step, receiving requests on/off, job invitations and bookings, with Performance and work
 * history beside them. The profile is on /worker/profile; identity and phone verification keep their own pages. One
 * compact notice appears only while something blocks taking jobs (identity that does not count here, an incomplete
 * profile); a staff restriction has its own notice.
 */
export function WorkerDashboardPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { hash } = useLocation();
  const base = useLoad((signal) => workersApi.fetchWorker(signal));

  if (MOVED[hash]) return <Navigate to={MOVED[hash]} replace />;
  if (!user) return null;
  if (base.state.status === "loading") return <PageLoader />;
  if (base.state.status === "error") return <LoadError error={base.state.error} onRetry={base.retry} />;
  const dashboard = base.state.data;
  // Unfinished onboarding resumes at the right screen (after a refresh or a new login).
  if (!dashboard.onboarding.complete && dashboard.onboarding.next_step) {
    return <Navigate to={onboardingPath(dashboard.onboarding.next_step)} replace />;
  }

  const { profile, identity, eligibility } = dashboard;
  const reason = (code: string) => (isTranslationKey(`worker.eligibility.reason.${code}`) ? t(`worker.eligibility.reason.${code}` as never) : code);
  const identityReason = eligibility.reasons.find((code) => IDENTITY_REASONS.has(code));
  const needsIdentity = !identity.counts_here;
  const profileIncomplete = eligibility.reasons.includes("profile_incomplete");

  return (
    <div className="space-y-5">
      <section aria-labelledby="worker-title" className="hero on-dark flex min-h-[11rem] items-center px-5 py-6 sm:min-h-[13rem] sm:px-8"
        style={{ "--hero-image": `url(${heroImage})` } as CSSProperties}>
        <div className="relative max-w-[68%] space-y-2 sm:max-w-[60%]">
          <h1 id="worker-title" className="font-display text-2xl text-white sm:text-3xl">{t("worker.dashboard.title")}</h1>
          <p className="text-sm text-[#dee7ff]">{t("worker.dashboard.subtitle")}</p>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/30 bg-white/10 px-3 py-0.5 text-sm font-bold">
            <HardHat className="size-4" aria-hidden />
            {t("role.worker.badge")}
          </span>
          <p className="flex flex-wrap items-center gap-1.5 text-sm text-[#dee7ff]">
            <span>{t("home.signedInAs")}</span>
            <Ltr>{user.phone_number_masked}</Ltr>
          </p>
        </div>
      </section>

      <AccountNotices />
      {needsIdentity && (
        <Alert tone="warning" title={t("worker.verifyNotice.title")}>
          <p>{identityReason ? reason(identityReason) : t("worker.verifyNotice.body")}</p>
          {identity.status !== "suspended" && (
            <ButtonLink to={PATHS.workerVerify} variant="ghost" className="min-h-11 px-0" icon={<ShieldAlert className="size-5" aria-hidden />}>
              {identity.status === "in_progress" || identity.status === "no_match" ? t("worker.identity.continue") : t("worker.verifyNotice.action")}
            </ButtonLink>
          )}
        </Alert>
      )}
      {profileIncomplete && (
        <Alert tone="warning" title={t("worker.profileNotice.title")}>
          <p>{reason("profile_incomplete")}</p>
          <ButtonLink to={PATHS.workerProfile} variant="ghost" className="min-h-11 px-0" icon={<UserRoundPen className="size-5" aria-hidden />}>
            {t("nav.profile")}
          </ButtonLink>
        </Alert>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.75fr)_minmax(17rem,1fr)]">
        <div className="min-w-0 space-y-5">
          <WorkerNextStep dashboard={dashboard} />
          <ReceivingCard accepting={profile.accepting_requests}
            onToggle={async () => base.set(await workersApi.setAcceptingRequests(!profile.accepting_requests))} />
          <InvitationInbox />
          <BookingList />
        </div>
        <div className="min-w-0 space-y-5">
          <WorkerPerformance />
          <WorkerFeedback />
          <Link to={PATHS.catalog} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
            <List className="size-5" aria-hidden />
            {t("landing.catalogLink")}
          </Link>
        </div>
      </div>
    </div>
  );
}
