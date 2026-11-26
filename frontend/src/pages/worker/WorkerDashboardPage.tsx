import { BadgeCheck, CirclePause, CirclePlay, HardHat, IdCard, List, MapPin, Mic, Pencil, Phone, ShieldCheck, Wrench } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, Navigate } from "react-router";

import * as catalogApi from "../../api/catalog";
import * as workersApi from "../../api/workers";
import { useAuth } from "../../auth/context";
import { PATHS } from "../../auth/paths";
import { Ltr } from "../../components/Ltr";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge, type BadgeTone } from "../../components/ui/StatusBadge";
import { PhoneConfirmationBadge } from "../../features/phone/PhoneConfirmationStatus";
import { label, LoadError, onboardingPath, useLoad } from "../../features/worker/shared";
import { isTranslationKey, useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";

const IDENTITY_TONE: Record<workersApi.IdentityStatus, BadgeTone> = {
  not_started: "neutral",
  in_progress: "info",
  no_match: "danger",
  demo_approved: "warning",
  provider_verified: "success",
  manually_reviewed: "success",
  rejected: "danger",
  expired: "danger",
  suspended: "danger",
};

function Card({ id, title, icon, children }: { id: string; title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
      <h2 id={id} className="flex items-center gap-2 text-lg font-bold">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * Worker dashboard (M4). Usable without identity verification. Profile completion, identity
 * status and the worker's own "accepting requests" choice are shown separately; the
 * eligibility card explains, from the server's check, why the worker can or cannot take jobs.
 */
export function WorkerDashboardPage() {
  const { t, language } = useI18n();
  const { user } = useAuth();
  const base = useLoad((signal) =>
    Promise.all([workersApi.fetchWorker(signal), catalogApi.fetchAllServiceTags(signal), catalogApi.fetchTrades(signal), catalogApi.fetchAreas(signal)]),
  );
  const [toggleError, setToggleError] = useState<unknown>(null);
  const [toggling, setToggling] = useState(false);

  if (!user) return null;
  if (base.state.status === "loading") return <PageLoader />;
  if (base.state.status === "error") return <LoadError error={base.state.error} onRetry={base.retry} />;
  const [dashboard, services, trades, areas] = base.state.data;
  // Unfinished onboarding resumes at the right screen (after a refresh or a new login).
  if (!dashboard.onboarding.complete && dashboard.onboarding.next_step) {
    return <Navigate to={onboardingPath(dashboard.onboarding.next_step)} replace />;
  }

  const { profile, identity, eligibility } = dashboard;
  const serviceLabel = (code: string) => {
    const found = services.results.find((item) => item.code === code);
    return found ? label(found.labels, language) : code;
  };
  const tradeItem = trades.results.find((item) => item.code === profile.trade);
  const areaItems = areas.results.filter((area) => profile.service_areas.includes(area.code));
  const cityItem = areas.results.find((area) => area.city.code === profile.city)?.city;
  const verified = identity.counts_here;
  const reasonText = (reason: string) => {
    const key = `worker.eligibility.reason.${reason}`;
    return isTranslationKey(key) ? t(key) : reason;
  };

  async function toggleAccepting() {
    setToggleError(null);
    setToggling(true);
    try {
      base.set([await workersApi.setAcceptingRequests(!profile.accepting_requests), services, trades, areas]);
    } catch (error) {
      setToggleError(error);
    } finally {
      setToggling(false);
    }
  }

  const summaryRow = (title: string, values: string[]) => (
    <div>
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{values.length ? values.join(language === "ur" ? "، " : ", ") : "—"}</dd>
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-primary">{t("worker.dashboard.title")}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="info" icon={<HardHat className="size-4" aria-hidden />}>{t("role.worker.badge")}</StatusBadge>
          {user.is_demo && <StatusBadge tone="warning">{t("demo.accountBadge")}</StatusBadge>}
        </div>
        <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
          <span>{t("home.signedInAs")}</span>
          <Ltr>{user.phone_number_masked}</Ltr>
        </p>
      </div>

      <Card id="eligibility-heading" title={t("worker.eligibility.heading")} icon={<BadgeCheck className="size-5" aria-hidden />}>
        <StatusBadge tone={eligibility.can_take_jobs ? "success" : "neutral"}>
          {eligibility.can_take_jobs ? t("worker.eligibility.yes") : t("worker.eligibility.no")}
        </StatusBadge>
        {eligibility.reasons.length > 0 && (
          <ul className="list-inside list-disc space-y-1">
            {eligibility.reasons.map((reason) => (
              <li key={reason}>{reasonText(reason)}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card id="identity-heading" title={t("worker.identity.heading")} icon={<IdCard className="size-5" aria-hidden />}>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={IDENTITY_TONE[identity.status]}>{t(`worker.identity.status.${identity.status}`)}</StatusBadge>
        </div>
        {identity.masked_cnic && (
          <p className="flex flex-wrap items-center gap-1.5 text-sm">
            <span>{t("worker.identity.masked")}</span>
            <Ltr>{identity.masked_cnic}</Ltr>
          </p>
        )}
        {identity.status === "demo_approved" && <Alert tone="demo">{t("worker.identity.demoNote")}</Alert>}
        {!dashboard.identity_provider.available && !verified && <p className="text-sm text-muted">{t("worker.identity.unavailable")}</p>}
        {!verified && identity.status !== "suspended" && (
          <ButtonLink to={PATHS.workerVerify} icon={<ShieldCheck className="size-5" aria-hidden />} fullWidth>
            {identity.status === "in_progress" || identity.status === "no_match" ? t("worker.identity.continue") : t("worker.identity.cta")}
          </ButtonLink>
        )}
      </Card>

      <Card id="profile-heading" title={t("worker.profile.heading")} icon={<Wrench className="size-5" aria-hidden />}>
        <StatusBadge tone={dashboard.onboarding.complete ? "success" : "neutral"}>
          {dashboard.onboarding.complete ? t("worker.profile.complete") : t("worker.profile.incomplete")}
        </StatusBadge>
        <dl className="space-y-2">
          {summaryRow(t("worker.profile.trade"), tradeItem ? [label(tradeItem.labels, language)] : [])}
          {summaryRow(t("worker.profile.services"), profile.services_offered.map(serviceLabel))}
          {summaryRow(t("worker.profile.main"), profile.primary_specialities.map(serviceLabel))}
          {profile.services_not_offered.length > 0 && summaryRow(t("worker.profile.excluded"), profile.services_not_offered.map(serviceLabel))}
          {summaryRow(t("onboarding.areas.cityLabel"), cityItem ? [label(cityItem.labels, language)] : [])}
          {summaryRow(t("worker.profile.areas"), areaItems.map((area) => label(area.labels, language)))}
        </dl>
        <p className="text-sm text-muted">{t("worker.profile.declarationNote")}</p>
        <div className="flex flex-wrap gap-2">
          <ButtonLink to={PATHS.workerWork} variant="secondary" icon={<Pencil className="size-5" aria-hidden />}>
            {t("worker.profile.editWork")}
          </ButtonLink>
          <ButtonLink to={PATHS.workerAreas} variant="secondary" icon={<MapPin className="size-5" aria-hidden />}>
            {t("worker.profile.editAreas")}
          </ButtonLink>
        </div>
      </Card>

      <Card id="accepting-heading" title={t("worker.accepting.label")} icon={profile.accepting_requests ? <CirclePlay className="size-5" aria-hidden /> : <CirclePause className="size-5" aria-hidden />}>
        <StatusBadge tone={profile.accepting_requests ? "success" : "neutral"}>
          {profile.accepting_requests ? t("worker.accepting.on") : t("worker.accepting.off")}
        </StatusBadge>
        <p className="text-sm text-muted">{t("worker.accepting.help")}</p>
        {toggleError !== null && <Alert tone="danger">{describeError(toggleError, t)}</Alert>}
        <Button
          variant="secondary"
          loading={toggling}
          loadingLabel={t("onboarding.saving")}
          icon={profile.accepting_requests ? <CirclePause className="size-5" aria-hidden /> : <CirclePlay className="size-5" aria-hidden />}
          onClick={() => void toggleAccepting()}
        >
          {profile.accepting_requests ? t("worker.accepting.turnOff") : t("worker.accepting.turnOn")}
        </Button>
      </Card>

      <Card id="phone-heading" title={t("home.phoneStatus")} icon={<Phone className="size-5" aria-hidden />}>
        <PhoneConfirmationBadge confirmation={user.phone_confirmation} />
        <div>
          <ButtonLink to={PATHS.phone} variant="secondary" icon={<ShieldCheck className="size-5" aria-hidden />}>
            {t("home.managePhone")}
          </ButtonLink>
        </div>
      </Card>

      <div className="flex flex-col gap-1">
        <Link to={PATHS.voiceTest} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
          <Mic className="size-5" aria-hidden />
          {t("worker.voiceIntro")}
        </Link>
        <Link to={PATHS.catalog} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
          <List className="size-5" aria-hidden />
          {t("landing.catalogLink")}
        </Link>
      </div>
    </div>
  );
}
