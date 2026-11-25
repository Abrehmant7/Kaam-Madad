import { type ReactNode, useCallback, useLayoutEffect, useMemo, useState } from "react";

import { I18nContext, type I18nContextValue, interpolate, RESOURCES } from "./context";
import { DEFAULT_LANGUAGE, isLanguage, LANGUAGE_META, type Language, type TranslationKey, type TranslationParams } from "./types";

const STORAGE_KEY = "rr.language";

// Browser storage can be unavailable (private mode, blocked site data), so
// every access is guarded. M2 will also sync this with the account's
// server-side preferred_language.
function readStoredLanguage(): Language | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

function storeLanguage(language: Language): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Not fatal: the choice simply won't persist on this device.
  }
}

interface I18nProviderProps {
  children: ReactNode;
  /** Overrides the stored/default language (used by tests). */
  initialLanguage?: Language;
}

export function I18nProvider({ children, initialLanguage }: I18nProviderProps) {
  const [language, setLanguageState] = useState<Language>(
    () => initialLanguage ?? readStoredLanguage() ?? DEFAULT_LANGUAGE,
  );
  const dir = LANGUAGE_META[language].dir;

  // Keep <html lang/dir> in sync so the browser applies RTL layout, Urdu
  // shaping, and screen-reader pronunciation for the whole document. A layout
  // effect applies it in the same commit as the new text (no wrong-direction frame).
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.lang = language;
    root.dir = dir;
  }, [language, dir]);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    storeLanguage(next);
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: TranslationParams) => interpolate(RESOURCES[language][key], params),
    [language],
  );

  const value = useMemo<I18nContextValue>(() => ({ language, dir, t, setLanguage }), [language, dir, t, setLanguage]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
