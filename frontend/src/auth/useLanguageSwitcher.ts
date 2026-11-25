import { useCallback } from "react";

import { updateLanguage } from "../api/auth";
import { useI18n } from "../i18n/context";
import type { Language } from "../i18n/types";
import { useAuth } from "./context";

/**
 * Change the UI language immediately (and on this device). When signed in, also
 * save it to the account so other devices and future logins use it. If saving
 * fails, the device keeps the new language and the account value is applied
 * again at the next login (documented rule).
 */
export function useLanguageSwitcher() {
  const { setLanguage } = useI18n();
  const { user, setUser } = useAuth();

  return useCallback(
    async (language: Language): Promise<boolean> => {
      setLanguage(language);
      if (!user || user.preferred_language === language) return true;
      try {
        const session = await updateLanguage(language);
        if (session.user) setUser(session.user);
        return true;
      } catch {
        return false;
      }
    },
    [setLanguage, user, setUser],
  );
}
