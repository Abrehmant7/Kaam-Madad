import { ApiError, ConnectionError } from "../api/client";
import { type I18nContextValue, isTranslationKey } from "./context";

type T = I18nContextValue["t"];

/** Translate any request failure into user-facing text, chosen by stable code. */
export function describeError(error: unknown, t: T): string {
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

/** Field errors from an ApiError as translated messages, keyed by field name. */
export function fieldErrorsOf(error: unknown, t: T): Record<string, string[]> {
  if (!(error instanceof ApiError)) return {};
  const result: Record<string, string[]> = {};
  for (const [field, items] of Object.entries(error.fields)) {
    result[field] = items.map((item) => fieldErrorText(item.code, t));
  }
  return result;
}
