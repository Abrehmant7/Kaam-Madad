import { LogIn, ShieldCheck, UserPlus } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import type { Role } from "../api/auth";
import { useAuth } from "../auth/context";
import { PATHS } from "../auth/paths";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { IconTileGroup } from "../components/ui/IconTile";
import { PasswordField, TextField } from "../components/ui/TextField";
import { InstructionAudio } from "../features/instructions/InstructionAudio";
import { StepHeader } from "../features/worker/shared";
import { useI18n } from "../i18n/context";
import { describeError, fieldErrorCodes, LocalMessage, translateFieldCodes } from "../i18n/errors";
import { LANGUAGE_META } from "../i18n/types";
import { isRole, roleOptions } from "./roleOptions";

type Errors = Record<string, string[]>;

export function SignupPage() {
  const { t, language } = useI18n();
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const initialRole = params.get("role");

  const [role, setRole] = useState<Role[]>(isRole(initialRole) ? [initialRole] : []);
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  // Codes and error objects, translated at render so they follow a language switch.
  const [errorCodes, setErrorCodes] = useState<Errors>({});
  const [formError, setFormError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const errors = translateFieldCodes(errorCodes, t);

  function validateLocally(): Errors {
    // Supplementary only; the server validates everything again.
    const result: Errors = {};
    if (role.length === 0) result.role = ["invalid_choice"];
    if (!phone.trim()) result.phone_number = ["required"];
    if (!password) result.password = ["required"];
    if (!passwordConfirm) result.password_confirm = ["required"];
    else if (password && password !== passwordConfirm) result.password_confirm = ["password_mismatch"];
    return result;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const local = validateLocally();
    setErrorCodes(local);
    if (Object.keys(local).length > 0 || !role[0]) {
      setFormError(new LocalMessage("errors.validation_error"));
      return;
    }
    setSubmitting(true);
    try {
      await signup({
        phone_number: phone,
        password,
        password_confirm: passwordConfirm,
        role: role[0],
        preferred_language: language,
      });
      // Workers continue straight to onboarding screen 2; customers go to their dashboard.
      // Phone confirmation is offered on both dashboards.
      navigate(role[0] === "worker" ? PATHS.workerWork : PATHS.customer, { replace: true });
    } catch (error) {
      setErrorCodes(fieldErrorCodes(error));
      setFormError(error);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} noValidate className="card mx-auto max-w-lg space-y-5 p-5 sm:p-7">
      {role[0] === "worker" ? (
        <StepHeader step={1} flow="worker" title={t("signup.title")} />
      ) : (
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("signup.title")}</h1>
      )}

      {formError !== null && <Alert tone="danger">{describeError(formError, t)}</Alert>}

      <IconTileGroup
        label={t("signup.roleLabel")}
        mode="single"
        options={roleOptions(t)}
        value={role}
        onChange={setRole}
        errors={errors.role}
      />

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
        hint={t("signup.passwordHint")}
        value={password}
        onChange={setPassword}
        errors={errors.password}
        autoComplete="new-password"
        maxLength={128}
        required
      />
      <InstructionAudio id="signup_password" />
      <PasswordField
        label={t("signup.passwordConfirmLabel")}
        value={passwordConfirm}
        onChange={setPasswordConfirm}
        errors={errors.password_confirm}
        autoComplete="new-password"
        maxLength={128}
        required
      />

      <div className="space-y-1 text-sm text-muted">
        <p>{t("signup.languageNote", { language: LANGUAGE_META[language].nativeName })}</p>
        <p className="flex items-center gap-1.5">
          <ShieldCheck className="size-4 shrink-0" aria-hidden />
          {t("signup.privacyNote")}
        </p>
      </div>

      <Button
        type="submit"
        fullWidth
        loading={submitting}
        loadingLabel={t("signup.submitting")}
        icon={<UserPlus className="size-5" aria-hidden />}
      >
        {t("signup.submit")}
      </Button>

      <p className="flex flex-wrap items-center gap-2">
        <span>{t("start.haveAccount")}</span>
        <Link to={PATHS.login} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-primary underline-offset-4 hover:underline">
          <LogIn className="size-5" aria-hidden />
          {t("landing.login")}
        </Link>
      </p>
    </form>
  );
}
