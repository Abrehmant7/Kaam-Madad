import { Languages } from "lucide-react";

import { useLanguageSwitcher } from "../../auth/useLanguageSwitcher";
import { useI18n } from "../../i18n/context";
import { type Language, LANGUAGE_META } from "../../i18n/types";

/**
 * Persistent Urdu ⇄ English switch. The button shows the OTHER language's name
 * in its own script (e.g. "English" while in Urdu), so a reader of either
 * language can find it.
 */
export function LanguageSwitch() {
  const { language, t } = useI18n();
  const switchLanguage = useLanguageSwitcher();
  const target: Language = language === "ur" ? "en" : "ur";
  const targetName = LANGUAGE_META[target].nativeName;

  return (
    <button
      type="button"
      onClick={() => void switchLanguage(target)}
      aria-label={t("nav.changeLanguage", { language: targetName })}
      className="flex min-h-11 items-center gap-1.5 rounded-lg border border-white/40 px-3 text-sm font-bold hover:bg-white/10"
    >
      <Languages className="size-5" aria-hidden />
      <span lang={target} dir={LANGUAGE_META[target].dir}>
        {targetName}
      </span>
    </button>
  );
}
