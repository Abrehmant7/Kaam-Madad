import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { useI18n } from "../../i18n/context";

export interface TileOption<V extends string> {
  value: V;
  label: string;
  description?: string;
  icon: ReactNode;
  /** Optional language for the label (e.g. "اردو" inside English UI). */
  lang?: string;
}

interface IconTileGroupProps<V extends string> {
  /** Visible group label (also the accessible name). */
  label: string;
  options: TileOption<V>[];
  mode: "single" | "multiple";
  value: V[];
  onChange: (value: V[]) => void;
  columns?: 1 | 2;
  errors?: string[];
}

/**
 * Large icon + text choice tiles (used for role, language, and later the
 * speciality questions). Single mode behaves as a radio group, multiple mode as
 * toggle buttons. Selection is shown by border, background, a check icon AND a
 * text label — never by colour alone.
 */
export function IconTileGroup<V extends string>({
  label,
  options,
  mode,
  value,
  onChange,
  columns = 2,
  errors = [],
}: IconTileGroupProps<V>) {
  const { t } = useI18n();

  function toggle(option: V) {
    if (mode === "single") {
      onChange([option]);
    } else {
      onChange(value.includes(option) ? value.filter((item) => item !== option) : [...value, option]);
    }
  }

  return (
    <fieldset>
      <legend className="mb-2 font-bold">{label}</legend>
      <div
        // The fieldset/legend already names a multi-select group; only single mode needs a radiogroup.
        role={mode === "single" ? "radiogroup" : undefined}
        aria-label={mode === "single" ? label : undefined}
        className={`grid gap-3 ${columns === 2 ? "grid-cols-2" : "grid-cols-1"}`}
      >
        {options.map((option) => {
          const selected = value.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              role={mode === "single" ? "radio" : undefined}
              aria-checked={mode === "single" ? selected : undefined}
              aria-pressed={mode === "multiple" ? selected : undefined}
              onClick={() => toggle(option.value)}
              className={[
                "relative flex min-h-28 flex-col items-center justify-center gap-2 rounded-2xl border-2 p-3 text-center transition-colors",
                selected ? "border-primary bg-primary-soft shadow-sm" : "border-line bg-white hover:border-primary/50 hover:bg-[#f7f9ff]",
              ].join(" ")}
            >
              <span className={selected ? "text-primary" : "text-muted"}>{option.icon}</span>
              <span className="font-bold leading-snug" lang={option.lang}>
                {option.label}
              </span>
              {option.description && <span className="text-sm text-muted">{option.description}</span>}
              {selected && (
                <span className="absolute end-2 top-2 flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-xs font-bold text-white">
                  <Check className="size-3.5" aria-hidden />
                  {t("common.selected")}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {errors.length > 0 && (
        <ul className="mt-1 text-sm font-bold text-danger-strong">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}
