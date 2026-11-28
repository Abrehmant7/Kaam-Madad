import { LogIn, UserPlus } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useAuth } from "../auth/context";
import { homePathFor, PATHS, safeNextPath } from "../auth/paths";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { PasswordField, TextField } from "../components/ui/TextField";
import { useI18n } from "../i18n/context";
import { describeError, fieldErrorCodes, translateFieldCodes } from "../i18n/errors";

export function LoginPage() {
  const { t } = useI18n();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionExpired = params.get("expired") === "1";

  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  // Codes and error objects, translated at render so they follow a language switch.
  const [errorCodes, setErrorCodes] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const errors = translateFieldCodes(errorCodes, t);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const local: Record<string, string[]> = {};
    if (!phone.trim()) local.phone_number = ["required"];
    if (!password) local.password = ["required"];
    setErrorCodes(local);
    if (Object.keys(local).length > 0) return;

    setSubmitting(true);
    try {
      const user = await login(phone, password);
      const next = safeNextPath(params.get("next"));
      navigate(next ?? homePathFor(user), { replace: true });
    } catch (error) {
      setErrorCodes(fieldErrorCodes(error));
      setFormError(error);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} noValidate className="card mx-auto max-w-lg space-y-5 p-5 sm:p-7">
      <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("login.title")}</h1>

      {sessionExpired && !formError && <Alert tone="warning">{t("auth.sessionExpired")}</Alert>}
      {formError !== null && <Alert tone="danger">{describeError(formError, t)}</Alert>}

      <TextField
        label={t("signup.phoneLabel")}
        hint={t("signup.phoneHint")}
        value={phone}
        onChange={setPhone}
        errors={errors.phone_number}
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        dir="ltr"
        maxLength={40}
        required
      />
      <PasswordField
        label={t("signup.passwordLabel")}
        value={password}
        onChange={setPassword}
        errors={errors.password}
        autoComplete="current-password"
        maxLength={128}
        required
      />

      <Button
        type="submit"
        fullWidth
        loading={submitting}
        loadingLabel={t("login.submitting")}
        icon={<LogIn className="size-5" aria-hidden />}
      >
        {t("login.submit")}
      </Button>

      <p className="flex flex-wrap items-center gap-2">
        <span>{t("login.noAccount")}</span>
        <Link to={PATHS.start} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-primary underline-offset-4 hover:underline">
          <UserPlus className="size-5" aria-hidden />
          {t("login.createAccount")}
        </Link>
      </p>
    </form>
  );
}
