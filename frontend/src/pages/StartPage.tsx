import { ArrowRight, Languages, LogIn } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import type { Role } from "../api/auth";
import { PATHS } from "../auth/paths";
import { useLanguageSwitcher } from "../auth/useLanguageSwitcher";
import { Button } from "../components/ui/Button";
import { IconTileGroup } from "../components/ui/IconTile";
import { useI18n } from "../i18n/context";
import { type Language, LANGUAGE_META } from "../i18n/types";
import { roleOptions } from "./roleOptions";

/** Step 1 for new users: choose language (applies immediately) and marketplace role. */
export function StartPage() {
  const { t, language } = useI18n();
  const switchLanguage = useLanguageSwitcher();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role[]>([]);

  const languageOptions = (["ur", "en"] as Language[]).map((code) => ({
    value: code,
    label: LANGUAGE_META[code].nativeName,
    lang: code,
    icon: <Languages className="size-8" aria-hidden />,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-primary">{t("start.title")}</h1>

      <IconTileGroup
        label={t("start.languageHeading")}
        mode="single"
        options={languageOptions}
        value={[language]}
        onChange={([next]) => next && void switchLanguage(next)}
      />

      <IconTileGroup
        label={t("start.roleHeading", { app: t("app.name") })}
        mode="single"
        options={roleOptions(t)}
        value={role}
        onChange={setRole}
      />

      <Button
        fullWidth
        disabled={role.length === 0}
        icon={<ArrowRight className="size-5 rtl:-scale-x-100" aria-hidden />}
        onClick={() => role[0] && navigate(`${PATHS.signup}?role=${role[0]}`)}
      >
        {t("common.continue")}
      </Button>

      <p className="flex flex-wrap items-center gap-2">
        <span>{t("start.haveAccount")}</span>
        <Link to={PATHS.login} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-primary underline-offset-4 hover:underline">
          <LogIn className="size-5" aria-hidden />
          {t("landing.login")}
        </Link>
      </p>
    </div>
  );
}
