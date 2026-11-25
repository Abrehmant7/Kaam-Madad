import type { ReactNode } from "react";

/**
 * Isolates left-to-right content (phone numbers, amounts, codes, IDs) inside
 * Urdu right-to-left text so digits and symbols keep their order (UX-01).
 */
export function Ltr({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <bdi dir="ltr" className={`font-sans ${className}`.trim()}>
      {children}
    </bdi>
  );
}
