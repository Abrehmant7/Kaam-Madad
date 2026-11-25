import { InfoIcon } from "../components/icons";
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
    </div>
  );
}
