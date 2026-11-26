import { House, List, Mic, Phone, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/context";
import { PATHS } from "../auth/paths";
import { Ltr } from "../components/Ltr";
import { ButtonLink } from "../components/ui/Button";
import { StatusBadge } from "../components/ui/StatusBadge";
import { PhoneConfirmationBadge } from "../features/phone/PhoneConfirmationStatus";
import { useI18n } from "../i18n/context";
import type { TranslationKey } from "../i18n/types";

/**
 * Minimal role homes. They identify the signed-in role and list the next
 * features as NOT available yet — no sample jobs, workers or bookings.
 */
function RoleHome({ title, badge, nextKeys }: { title: string; badge: ReactNode; nextKeys: TranslationKey[] }) {
  const { t } = useI18n();
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-primary">{title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {badge}
          {user.is_demo && <StatusBadge tone="warning">{t("demo.accountBadge")}</StatusBadge>}
        </div>
        {/* Flex gap keeps the label/number spacing stable across the RTL/LTR boundary. */}
        <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
          <span>{t("home.signedInAs")}</span>
          <Ltr>{user.phone_number_masked}</Ltr>
        </p>
      </div>

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
        <h2 id="next-heading" className="text-lg font-bold">
          {t("home.nextHeading")}
        </h2>
        <p className="text-sm text-muted">{t("home.nextIntro")}</p>
        <ul className="space-y-2">
          {nextKeys.map((key) => (
            <li key={key} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2">
              <span>{t(key)}</span>
              <StatusBadge tone="neutral">{t("common.notAvailableYet")}</StatusBadge>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-col gap-1">
        <Link to={PATHS.voiceTest} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
          <Mic className="size-5" aria-hidden />
          {t("home.voiceTest")}
        </Link>
        <Link to={PATHS.catalog} className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
          <List className="size-5" aria-hidden />
          {t("landing.catalogLink")}
        </Link>
      </div>
    </div>
  );
}

export function CustomerHomePage() {
  const { t } = useI18n();
  return (
    <RoleHome
      title={t("home.customer.title")}
      badge={<StatusBadge tone="info" icon={<House className="size-4" aria-hidden />}>{t("role.customer.badge")}</StatusBadge>}
      nextKeys={["home.customer.next.describe", "home.customer.next.recommend", "home.customer.next.chat"]}
    />
  );
}

/** Accounts without a marketplace role (staff created in the admin). */
export function AccountHomePage() {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold text-primary">{t("home.noRole.title")}</h1>
      <p>{t("home.noRole.body")}</p>
      {/* Full page load: /admin/ is served by Django, not the SPA. */}
      <a href="/admin/" className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
        <ShieldCheck className="size-5" aria-hidden />
        {t("nav.adminSite")}
      </a>
    </div>
  );
}
