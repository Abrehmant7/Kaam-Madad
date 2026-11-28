import { type TextareaHTMLAttributes, useId } from "react";

import { FieldErrors } from "./TextField";

interface TextAreaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  errors?: string[];
}

/** Multi-line text input with label, hint and translated field errors. dir="auto" suits Urdu or English. */
export function TextArea({ label, value, onChange, hint, errors = [], id, rows = 4, ...props }: TextAreaProps) {
  const generated = useId();
  const inputId = id ?? generated;
  const describedBy = [hint ? `${inputId}-hint` : "", errors.length ? `${inputId}-errors` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={inputId} className="mb-1 block font-bold">
        {label}
      </label>
      {hint && (
        <p id={`${inputId}-hint`} className="mb-1 text-sm text-muted">
          {hint}
        </p>
      )}
      <textarea
        id={inputId}
        value={value}
        rows={rows}
        dir="auto"
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={errors.length > 0 || undefined}
        aria-describedby={describedBy}
        className={`w-full rounded-xl border bg-[#fbfcff] px-3 py-2 text-lg ${errors.length ? "border-2 border-danger" : "border-field focus:border-primary"}`}
        {...props}
      />
      <FieldErrors id={`${inputId}-errors`} messages={errors} />
    </div>
  );
}
