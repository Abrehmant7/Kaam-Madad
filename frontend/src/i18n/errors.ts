import { ApiError, ConnectionError } from "../api/client";
import { type I18nContextValue, isTranslationKey } from "./context";
import type { TranslationKey } from "./types";

type T = I18nContextValue["t"];

/**
 * A client-side message (e.g. local validation) stored by key, so it is translated
 * at render time like server errors. Components store errors/codes — never
 * translated strings — so messages follow a language switch.
 */
export class LocalMessage {
  constructor(readonly key: TranslationKey) {}
}

/** Translate any request failure into user-facing text, chosen by stable code. */
export function describeError(error: unknown, t: T): string {
  if (error instanceof LocalMessage) return t(error.key);
  if (error instanceof ConnectionError) {
    if (error.reason === "offline") return t("status.offline");
    if (error.reason === "timeout") return t("status.timeout");
    return t("status.unreachable");
  }
  if (error instanceof ApiError) {
    const key = `errors.${error.code}`;
    if (!isTranslationKey(key)) return t("errors.unexpected");
    const details = error.details;
    const retry = Number(details.retry_after_seconds ?? 0);
    return t(key, {
      seconds: retry,
      minutes: Math.max(1, Math.ceil(retry / 60)),
      attempts: Number(details.attempts_remaining ?? 0),
    });
  }
  return t("errors.unexpected");
}

/** Translate a server field-error code (falls back to a generic message). */
export function fieldErrorText(code: string, t: T): string {
  const key = `fieldErrors.${code}`;
  return isTranslationKey(key) ? t(key) : t("fieldErrors.invalid");
}

/**
 * Field error CODES from an ApiError, keyed by field name (``prefix`` strips e.g. "fields.").
 * Store codes, not translated text, so messages follow a later language switch.
 */
export function fieldErrorCodes(error: unknown, prefix = ""): Record<string, string[]> {
  if (!(error instanceof ApiError)) return {};
  const result: Record<string, string[]> = {};
  for (const [field, items] of Object.entries(error.fields)) {
    const name = prefix && field.startsWith(prefix) ? field.slice(prefix.length) : field;
    result[name] = items.map((item) => item.code);
  }
  return result;
}

/** Translate a {field: codes[]} map at render time. */
export function translateFieldCodes(codes: Record<string, string[]>, t: T): Record<string, string[]> {
  return Object.fromEntries(Object.entries(codes).map(([field, list]) => [field, list.map((code) => fieldErrorText(code, t))]));
}
