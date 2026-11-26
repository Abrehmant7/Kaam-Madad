/**
 * Text direction by the script that dominates. ``dir="auto"`` looks only at the FIRST strong
 * letter, so Urdu that starts with "G-9" or "AC" would be laid out left-to-right.
 */
const ARABIC_SCRIPT = /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]/g;
const LATIN = /[A-Za-z]/g;

export function textDir(text: string): "rtl" | "ltr" | "auto" {
  const arabic = (text.match(ARABIC_SCRIPT) ?? []).length;
  const latin = (text.match(LATIN) ?? []).length;
  if (!arabic && !latin) return "auto";
  return arabic >= latin ? "rtl" : "ltr";
}

/**
 * Keep a left-to-right fragment (times, numbers) in order inside a translated Urdu sentence,
 * using Unicode isolate marks (LRI … PDI). The server strips them before speech synthesis.
 */
export function isolateLtr(text: string): string {
  return `\u2066${text}\u2069`;
}
