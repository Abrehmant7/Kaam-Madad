/**
 * Preferred visit window helpers (JOB-03). The customer picks a date and start/end times as
 * Pakistan time; the API stores UTC. Pakistan has no daylight saving, so Asia/Karachi is a fixed
 * +05:00 offset, which makes the conversion exact and independent of the device's time zone.
 */

export const ZONE = "Asia/Karachi";
const OFFSET = "+05:00";

/** "2026-11-28" + "17:00" → "2026-11-28T17:00:00+05:00". */
export function toIso(date: string, time: string): string {
  return `${date}T${time}:00${OFFSET}`;
}

/** UTC ISO → { date: "YYYY-MM-DD", time: "HH:MM" } in Asia/Karachi. */
export function fromIso(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: "", time: "" };
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return { date: `${get("year")}-${get("month")}-${get("day")}`, time: `${get("hour")}:${get("minute")}` };
}

/** Today's date in Asia/Karachi plus ``days``, as YYYY-MM-DD (for the date picker's min/max). */
export function karachiDate(days = 0, now = new Date()): string {
  return fromIso(new Date(now.getTime() + days * 86_400_000).toISOString()).date;
}

const locale = (language: "ur" | "en") => (language === "ur" ? "ur-PK" : "en-GB");

/** "Friday 28 November 2026" in the UI language, Asia/Karachi. */
export function formatDate(iso: string, language: "ur" | "en"): string {
  return new Intl.DateTimeFormat(locale(language), { timeZone: ZONE, weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
}

/** "5:00 pm" in the UI language, Asia/Karachi. */
export function formatTime(iso: string, language: "ur" | "en"): string {
  return new Intl.DateTimeFormat(locale(language), { timeZone: ZONE, hour: "numeric", minute: "2-digit", hour12: true }).format(new Date(iso));
}
