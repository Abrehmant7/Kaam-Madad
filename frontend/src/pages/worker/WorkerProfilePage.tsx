import { IdCard, MapPin, Pencil, Phone, UserRound } from "lucide-react";
import { Navigate } from "react-router";

import * as catalogApi from "../../api/catalog";
import * as workersApi from "../../api/workers";
import { useAuth } from "../../auth/context";
import { PATHS } from "../../auth/paths";
import { ButtonLink } from "../../components/ui/Button";
import { PageHeader } from "../../components/ui/PageHeader";
import { PageLoader } from "../../components/ui/PageLoader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { PhoneConfirmationBadge } from "../../features/phone/PhoneConfirmationStatus";
import { label, LoadError, onboardingPath, useLoad } from "../../features/worker/shared";
import { useI18n } from "../../i18n/context";

/**
 * "My profile" (moved from the dashboard): the worker's own declarations — trade, services, main speciality,
 * services not offered, city and work areas — with Edit work and Edit areas. Identity and phone verification keep their
 * own pages; their status is linked here so they stay one tap away.
 */
export function WorkerProfilePage() {
  const { t, language } = useI18n();
  const { user } = useAuth();
  const data = useLoad((signal) =>
    Promise.all([workersApi.fetchWorker(signal), catalogApi.fetchAllServiceTags(signal), catalogApi.fetchTrades(signal), catalogApi.fetchAreas(signal)]),
  );
  if (!user) return null;
  if (data.state.status === "loading") return <PageLoader />;
  if (data.state.status === "error") return <LoadError error={data.state.error} onRetry={data.retry} />;
  const [dashboard, services, trades, areas] = data.state.data;
  if (!dashboard.onboarding.complete && dashboard.onboarding.next_step) {
    return <Navigate to={onboardingPath(dashboard.onboarding.next_step)} replace />;
  }
  const { profile, identity } = dashboard;
  const separator = language === "ur" ? "، " : ", ";
  const serviceLabel = (code: string) => {
    const found = services.results.find((item) => item.code === code);
    return found ? label(found.labels, language) : code;
  };
  const trade = trades.results.find((item) => item.code === profile.trade);
  const city = areas.results.find((area) => area.city.code === profile.city)?.city;
  const row = (title: string, values: string[]) => (
    <div className="min-w-0">
      <dt className="text-sm text-muted">{title}</dt>
      <dd className="font-bold">{values.length ? values.join(separator) : "—"}</dd>
    </div>
  );

  return (
    <div className="space-y-5">
      <PageHeader icon={<UserRound className="size-6" aria-hidden />} title={t("nav.profile")}>
        <StatusBadge tone={dashboard.onboarding.complete ? "success" : "neutral"}>
          {dashboard.onboarding.complete ? t("worker.profile.complete") : t("worker.profile.incomplete")}
        </StatusBadge>
      </PageHeader>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,22rem)]">
        <section aria-labelledby="profile-work" className="card space-y-4 p-4 sm:p-5">
          <h2 id="profile-work" className="text-lg font-bold">{t("worker.profile.heading")}</h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            {row(t("worker.profile.trade"), trade ? [label(trade.labels, language)] : [])}
            {row(t("worker.profile.main"), profile.primary_specialities.map(serviceLabel))}
            {row(t("worker.profile.services"), profile.services_offered.map(serviceLabel))}
            {profile.services_not_offered.length > 0 && row(t("worker.profile.excluded"), profile.services_not_offered.map(serviceLabel))}
            {row(t("onboarding.areas.cityLabel"), city ? [label(city.labels, language)] : [])}
            {row(t("worker.profile.areas"), areas.results.filter((area) => profile.service_areas.includes(area.code)).map((area) => label(area.labels, language)))}
          </dl>
          <p className="text-sm text-muted">{t("worker.profile.declarationNote")}</p>
          <div className="flex flex-wrap gap-2">
            <ButtonLink to={PATHS.workerWork} variant="secondary" icon={<Pencil className="size-5" aria-hidden />}>{t("worker.profile.editWork")}</ButtonLink>
            <ButtonLink to={PATHS.workerAreas} variant="secondary" icon={<MapPin className="size-5" aria-hidden />}>{t("worker.profile.editAreas")}</ButtonLink>
          </div>
        </section>

        <aside aria-label={t("nav.account")} className="card space-y-4 p-4">
          <div className="space-y-2">
            <h2 className="flex items-center gap-2 font-bold"><IdCard className="size-5 text-primary" aria-hidden />{t("worker.identity.heading")}</h2>
            <StatusBadge tone={identity.counts_here ? "success" : "neutral"}>{t(`worker.identity.status.${identity.status}`)}</StatusBadge>
            <div><ButtonLink to={PATHS.workerVerify} variant="ghost" className="min-h-11 px-0">{t("nav.verify")}</ButtonLink></div>
          </div>
          <div className="space-y-2 border-t border-line pt-3">
            <h2 className="flex items-center gap-2 font-bold"><Phone className="size-5 text-primary" aria-hidden />{t("home.phoneStatus")}</h2>
            <PhoneConfirmationBadge confirmation={user.phone_confirmation} />
            <div><ButtonLink to={PATHS.phone} variant="ghost" className="min-h-11 px-0">{t("home.managePhone")}</ButtonLink></div>
          </div>
        </aside>
      </div>
    </div>
  );
}
