import type { SVGProps } from "react";

// Small inline icons. They are decorative (aria-hidden) and always paired with
// visible text: an icon alone never conveys a decision or state (UX-02).
type IconProps = SVGProps<SVGSVGElement>;

function BaseIcon({ children, className = "size-6", ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...props}
    >
      {children}
    </svg>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.5 2.5 2.5L16 9.5" />
    </BaseIcon>
  );
}

export function WarningIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M12 3.5 2.5 20h19L12 3.5Z" />
      <path d="M12 10v4" />
      <path d="M12 17.25h.01" />
    </BaseIcon>
  );
}

export function NoConnectionIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M2.5 9a14 14 0 0 1 19 0" />
      <path d="M6 12.5a9 9 0 0 1 12 0" />
      <path d="M9.5 16a4 4 0 0 1 5 0" />
      <path d="M12 19.5h.01" />
      <path d="m3 3 18 18" />
    </BaseIcon>
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M20 11a8 8 0 0 0-14.5-4.5L4 8" />
      <path d="M4 4v4h4" />
      <path d="M4 13a8 8 0 0 0 14.5 4.5L20 16" />
      <path d="M20 20v-4h-4" />
    </BaseIcon>
  );
}

export function SpinnerIcon({ className = "size-6", ...props }: IconProps) {
  return (
    <BaseIcon className={`${className} motion-safe:animate-spin`} {...props}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </BaseIcon>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.75h.01" />
    </BaseIcon>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3.5 11 12 4l8.5 7" />
      <path d="M5.5 9.5V20h13V9.5" />
      <path d="M10 20v-5h4v5" />
    </BaseIcon>
  );
}

/** Brand mark: a house with a wrench, on indigo, with a gold base line. */
export function LogoMark({ className = "size-9", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false" className={className} {...props}>
      <rect width="48" height="48" rx="12" fill="#234cb7" />
      <g fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 32V21l12-9 12 9v11H24" />
        <path d="M20 34l8-8m-3.7-3.7 7.4 7.4" />
      </g>
      <path d="M11 36h9" stroke="#ffc75f" strokeWidth="3.2" strokeLinecap="round" />
    </svg>
  );
}
