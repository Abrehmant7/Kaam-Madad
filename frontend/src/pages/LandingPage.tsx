import { HardHat, House, List, LogIn } from "lucide-react";
import { Link } from "react-router";

import { PATHS } from "../auth/paths";
import { InfoIcon } from "../components/icons";
import { ButtonLink } from "../components/ui/Button";
import { ServerStatusCard } from "../features/health/ServerStatusCard";
import { useI18n } from "../i18n/context";

export function LandingPage() {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <section aria-labelledby="landing-title" className="space-y-3">
        <h1 id="landing-title" className="text-3xl font-bold text-primary">
          {t("landing.title")}
        </h1>
        <p className="text-lg font-bold text-ink">{t("app.tagline")}</p>
        <p className="text-muted">{t("landing.intro")}</p>
      </section>

      <div className="grid gap-3">
        <ButtonLink to={`${PATHS.signup}?role=worker`} icon={<HardHat className="size-5" aria-hidden />} fullWidth>
          {t("landing.needWork")}
        </ButtonLink>
        <ButtonLink to={`${PATHS.signup}?role=customer`} icon={<House className="size-5" aria-hidden />} fullWidth>
          {t("landing.needWorker")}
        </ButtonLink>
        <ButtonLink to={PATHS.login} variant="secondary" icon={<LogIn className="size-5" aria-hidden />} fullWidth>
          {t("landing.login")}
        </ButtonLink>
      </div>

      <aside
        aria-labelledby="dev-notice-title"
        className="flex items-start gap-3 rounded-2xl border border-accent/60 bg-accent-soft p-4"
      >
        <InfoIcon className="mt-1 size-6 shrink-0 text-warning-strong" />
        <div>
          <h2 id="dev-notice-title" className="font-bold">
            {t("landing.devNotice.title")}
          </h2>
          <p>{t("landing.devNotice.body")}</p>
        </div>
      </aside>

      <ServerStatusCard />

      <Link to={PATHS.catalog} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
        <List className="size-5" aria-hidden />
        {t("landing.catalogLink")}
      </Link>
    </div>
  );
}
