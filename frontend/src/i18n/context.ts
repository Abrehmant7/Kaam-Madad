import { createContext, useContext } from "react";

import { en } from "./resources/en";
import { ur } from "./resources/ur";
import type { Language, TextDirection, TranslationKey, TranslationParams, Translations } from "./types";

export const RESOURCES: Record<Language, Translations> = { ur, en };

export interface I18nContextValue {
  language: Language;
  dir: TextDirection;
  t: (key: TranslationKey, params?: TranslationParams) => string;
  setLanguage: (language: Language) => void;
}

export const I18nContext = createContext<I18nContextValue | null>(null);

/** Replace `{name}` placeholders with values from `params`. */
export function interpolate(template: string, params?: TranslationParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
  );
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used inside <I18nProvider>.");
  }
  return value;
}
