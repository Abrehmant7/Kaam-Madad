import { FileCheck2, HardHat, House, List, LogIn, Mic, UsersRound } from "lucide-react";
import type { CSSProperties } from "react";
import { Link } from "react-router";

import heroImage from "../assets/hero-electrician.webp";
import { PATHS } from "../auth/paths";
import { InfoIcon } from "../components/icons";
import { ButtonLink } from "../components/ui/Button";
import { ServerStatusCard } from "../features/health/ServerStatusCard";
import { useI18n } from "../i18n/context";

/** Landing: two clear entry points ("I need work" / "I need a worker"), then how it works. No sample people or numbers. */
export function LandingPage() {
  const { t } = useI18n();
  const steps = [
    { icon: <Mic className="size-6" aria-hidden />, title: t("landing.how.1.title"), body: t("landing.how.1.body") },
    { icon: <UsersRound className="size-6" aria-hidden />, title: t("landing.how.2.title"), body: t("landing.how.2.body") },
    { icon: <FileCheck2 className="size-6" aria-hidden />, title: t("landing.how.3.title"), body: t("landing.how.3.body") },
  ];

  return (
    <div className="space-y-6">
      <section aria-labelledby="landing-title" className="hero on-dark flex min-h-[18rem] items-center px-5 py-7 sm:min-h-[21rem] sm:px-9"
        style={{ "--hero-image": `url(${heroImage})` } as CSSProperties}>
        <div className="relative max-w-[68%] space-y-3 sm:max-w-[60%]">
          <h1 id="landing-title" className="font-display text-2xl text-white sm:text-4xl">
            {t("landing.title")}
          </h1>
          <p className="max-w-md text-sm text-[#dee7ff] sm:text-base">{t("app.tagline")}</p>
          <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:flex-wrap">
            <ButtonLink to={`${PATHS.signup}?role=worker`} variant="gold" icon={<HardHat className="size-5" aria-hidden />}>
              {t("landing.needWork")}
            </ButtonLink>
            <ButtonLink to={`${PATHS.signup}?role=customer`} variant="secondary" className="border-white bg-white" icon={<House className="size-5" aria-hidden />}>
              {t("landing.needWorker")}
            </ButtonLink>
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2">
        <Link to={`${PATHS.signup}?role=worker`} className="card flex items-start gap-3 p-4 hover:border-primary/50">
          <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-accent-soft text-warning-strong"><HardHat className="size-6" aria-hidden /></span>
          <span>
            <span className="block text-lg font-bold">{t("landing.needWork")}</span>
            <span className="block text-sm text-muted">{t("landing.needWork.hint")}</span>
          </span>
        </Link>
        <Link to={`${PATHS.signup}?role=customer`} className="card flex items-start gap-3 p-4 hover:border-primary/50">
          <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-primary-soft text-primary"><House className="size-6" aria-hidden /></span>
          <span>
            <span className="block text-lg font-bold">{t("landing.needWorker")}</span>
            <span className="block text-sm text-muted">{t("landing.needWorker.hint")}</span>
          </span>
        </Link>
      </div>

      <p className="flex flex-wrap items-center gap-2">
        <span>{t("start.haveAccount")}</span>
        <Link to={PATHS.login} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-primary underline-offset-4 hover:underline">
          <LogIn className="size-5 rtl:-scale-x-100" aria-hidden />
          {t("landing.login")}
        </Link>
      </p>

      <section aria-labelledby="how-title" className="space-y-3">
        <h2 id="how-title" className="text-xl font-bold">{t("landing.how.title")}</h2>
        <ol className="grid gap-3 md:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title} className="card space-y-2 p-4">
              <span className="flex items-center gap-2 text-primary">
                {step.icon}
                <span className="font-sans text-sm font-bold" aria-hidden>{index + 1}</span>
              </span>
              <h3 className="font-bold">{step.title}</h3>
              <p className="text-sm text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <aside aria-labelledby="dev-notice-title" className="flex items-start gap-3 rounded-xl border border-accent/60 bg-accent-soft p-4">
        <InfoIcon className="mt-1 size-6 shrink-0 text-warning-strong" />
        <div>
          <h2 id="dev-notice-title" className="font-bold">{t("landing.devNotice.title")}</h2>
          <p>{t("landing.devNotice.body")}</p>
        </div>
      </aside>

      <div className="grid gap-3 md:grid-cols-2">
        <ServerStatusCard />
        <Link to={PATHS.catalog} className="card flex min-h-11 items-center gap-2 p-4 font-bold text-primary hover:border-primary/50">
          <List className="size-5" aria-hidden />
          {t("landing.catalogLink")}
        </Link>
      </div>
    </div>
  );
}
