import { CircleAlert, Eye, EyeOff } from "lucide-react";
import { type InputHTMLAttributes, type ReactNode, useId, useState } from "react";

import { useI18n } from "../../i18n/context";

/** Translated field errors with an icon; announced via aria-describedby. */
export function FieldErrors({ id, messages }: { id: string; messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <ul id={id} className="mt-1 space-y-1 text-sm font-bold text-danger-strong">
      {messages.map((message) => (
        <li key={message} className="flex items-start gap-1.5">
          <CircleAlert className="mt-1 size-4 shrink-0" aria-hidden />
          <span>{message}</span>
        </li>
      ))}
    </ul>
  );
}

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value" | "dir"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  errors?: string[];
  /** "ltr" for phone numbers and codes so digits never reorder inside Urdu UI. */
  dir?: "ltr" | "rtl" | "auto";
  trailing?: ReactNode;
}

export function TextField({ label, value, onChange, hint, errors = [], dir, trailing, id, className = "", ...props }: TextFieldProps) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-errors`;
  const describedBy = [hint ? hintId : "", errors.length ? errorId : ""].filter(Boolean).join(" ") || undefined;
  const invalid = errors.length > 0;

  return (
    <div className={className}>
      <label htmlFor={inputId} className="mb-1 block font-bold">
        {label}
      </label>
      {hint && (
        <p id={hintId} className="mb-1 text-sm text-muted">
          {hint}
        </p>
      )}
      <div className="relative">
        <input
          id={inputId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          dir={dir}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          className={[
            "min-h-12 w-full rounded-xl border-2 bg-white px-3 py-2 text-lg",
            dir === "ltr" ? "font-sans text-start" : "",
            trailing ? "pe-14" : "",
            invalid ? "border-danger" : "border-line focus:border-primary",
          ].join(" ")}
          {...props}
        />
        {trailing && <div className="absolute inset-y-0 end-1 flex items-center">{trailing}</div>}
      </div>
      <FieldErrors id={errorId} messages={errors} />
    </div>
  );
}

type PasswordFieldProps = Omit<TextFieldProps, "type" | "trailing" | "dir">;

/** Password input with an accessible show/hide toggle. */
export function PasswordField(props: PasswordFieldProps) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      {...props}
      type={visible ? "text" : "password"}
      dir="ltr"
      trailing={
        <button
          type="button"
          onClick={() => setVisible((value) => !value)}
          aria-pressed={visible}
          aria-label={visible ? t("password.hide") : t("password.show")}
          title={visible ? t("password.hide") : t("password.show")}
          className="flex size-11 items-center justify-center rounded-lg text-muted hover:text-ink"
        >
          {visible ? <EyeOff className="size-5" aria-hidden /> : <Eye className="size-5" aria-hidden />}
        </button>
      }
    />
  );
}
