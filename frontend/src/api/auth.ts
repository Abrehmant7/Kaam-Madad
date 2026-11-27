import type { Language } from "../i18n/types";
import { apiRequest } from "./client";

export type Role = "worker" | "customer";

export interface PhoneConfirmation {
  status: "confirmed" | "unconfirmed";
  /** "demo" is simulated and never real phone-ownership verification. */
  method: "demo" | "sms" | null;
  confirmed_at: string | null;
}

export interface AccountUser {
  id: string;
  phone_number_masked: string;
  role: Role | null;
  preferred_language: Language;
  is_demo: boolean;
  is_staff: boolean;
  /** M10: staff restriction — the account can view records, report and reply, but not start new activity. */
  restricted: boolean;
  phone_confirmation: PhoneConfirmation;
  date_joined: string;
}

export interface SessionResponse {
  authenticated: boolean;
  user: AccountUser | null;
}

export interface PhoneProviderStatus {
  provider: "demo" | "unconfigured";
  available: boolean;
  simulated: boolean;
}

export interface AiProviderStatus {
  provider: string;
  available: boolean;
  /** True for deterministic fixture results (demo deployments only). */
  simulated: boolean;
}

export interface ClientConfig {
  deployment_mode: "live" | "demo";
  phone_verification: PhoneProviderStatus;
  ai?: {
    speech_to_text: AiProviderStatus;
    interpretation: AiProviderStatus;
    text_to_speech: AiProviderStatus;
    cnic_ocr?: AiProviderStatus;
  };
  identity_verification?: AiProviderStatus;
  voice_limits?: { max_audio_bytes: number; max_audio_seconds: number; max_synthesis_chars: number };
  languages: Language[];
  default_language: Language;
}

export interface ActiveCode {
  id: string;
  method: "demo" | "sms";
  expires_at: string;
  expires_in_seconds: number;
  attempts_remaining: number;
  resend_available_in_seconds: number;
}

export interface PhoneConfirmationState {
  status: "confirmed" | "unconfirmed";
  method: "demo" | "sms" | null;
  confirmed_at: string | null;
  provider: PhoneProviderStatus;
  active_code: ActiveCode | null;
  /** Present only in demo deployments, only in the response that issued the code. */
  demo?: { code: string; notice: string };
}

export interface SignupPayload {
  phone_number: string;
  password: string;
  password_confirm: string;
  role: Role;
  preferred_language: Language;
}

export const fetchConfig = (signal?: AbortSignal) => apiRequest<ClientConfig>("/config/", { signal });

export const fetchMe = (signal?: AbortSignal) =>
  apiRequest<SessionResponse>("/auth/me/", { signal, skipUnauthorizedHandler: true });

export const signup = (payload: SignupPayload) =>
  apiRequest<SessionResponse>("/auth/signup/", { method: "POST", body: payload, skipUnauthorizedHandler: true });

export const login = (phone_number: string, password: string) =>
  apiRequest<SessionResponse>("/auth/login/", {
    method: "POST",
    body: { phone_number, password },
    skipUnauthorizedHandler: true,
  });

export const logout = () => apiRequest<void>("/auth/logout/", { method: "POST", skipUnauthorizedHandler: true });

export const updateLanguage = (preferred_language: Language) =>
  apiRequest<SessionResponse>("/auth/me/language/", { method: "PATCH", body: { preferred_language } });

export const fetchPhoneConfirmation = (signal?: AbortSignal) =>
  apiRequest<PhoneConfirmationState>("/auth/phone-confirmation/", { signal });

export const startPhoneConfirmation = () =>
  apiRequest<PhoneConfirmationState>("/auth/phone-confirmation/", { method: "POST" });

export const verifyPhoneCode = (code: string) =>
  apiRequest<SessionResponse>("/auth/phone-confirmation/verify/", { method: "POST", body: { code } });
