import { ShieldCheck } from "lucide-react";

import { useI18n } from "../i18n/context";

/** Accounts without a marketplace role (staff created in the admin). */
export function AccountHomePage() {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("home.noRole.title")}</h1>
      <p>{t("home.noRole.body")}</p>
      {/* Full page load: /admin/ is served by Django, not the SPA. */}
      <a href="/admin/" className="inline-flex min-h-11 items-center gap-2 font-bold text-primary underline-offset-4 hover:underline">
        <ShieldCheck className="size-5" aria-hidden />
        {t("nav.adminSite")}
      </a>
    </div>
  );
}
