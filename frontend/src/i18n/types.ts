import type { ur } from "./resources/ur";

export type Language = "ur" | "en";
export type TextDirection = "rtl" | "ltr";

export type TranslationKey = keyof typeof ur;
export type Translations = Record<TranslationKey, string>;
export type TranslationParams = Record<string, string | number>;

export interface LanguageMeta {
  dir: TextDirection;
  /** Name of the language written in that language (for the M2 language switch). */
  nativeName: string;
}

export const DEFAULT_LANGUAGE: Language = "ur";

export const LANGUAGE_META: Record<Language, LanguageMeta> = {
  ur: { dir: "rtl", nativeName: "اردو" },
  en: { dir: "ltr", nativeName: "English" },
};

export function isLanguage(value: unknown): value is Language {
  return value === "ur" || value === "en";
}
