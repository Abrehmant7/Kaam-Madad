import { useEffect, useState } from "react";

/**
 * Seconds remaining from a server-provided "seconds from now" value. Uses the
 * local clock only for elapsed time, so device clock skew does not matter.
 * Pass a new `key` (e.g. the code id) to restart.
 */
export function useCountdown(seconds: number | null, key: unknown): number {
  const [deadline, setDeadline] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setDeadline(seconds === null ? null : Date.now() + seconds * 1000);
    setNow(Date.now());
  }, [seconds, key]);

  useEffect(() => {
    if (deadline === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [deadline]);

  if (deadline === null) return 0;
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

/** m:ss for display inside an <Ltr> element. */
export function formatMinutesSeconds(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
