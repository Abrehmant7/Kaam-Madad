import { apiRequest } from "./client";

export type VoiceKind = "worker_introduction" | "job_description";
/** Upload purposes: the two interpretation kinds, plus conversation voice notes (never interpreted as drafts). */
export type ClipPurpose = VoiceKind | "message";
export type LanguageHint = "ur" | "en";

/** AI calls can take longer than ordinary requests (server retries are bounded). */
const AI_TIMEOUT_MS = 60_000;

export interface AudioClip {
  id: string;
  purpose: ClipPurpose;
  source: "recording" | "upload";
  mime_type: string;
  size_bytes: number;
  duration_seconds: number;
  created_at: string;
  content_url: string;
}

export interface Transcription {
  id: string;
  clip_id: string;
  /** Original transcript in the spoken language — never edited. */
  text: string;
  language: "ur" | "en" | "mixed" | "unknown";
  language_hint: string;
  no_speech: boolean;
  provider: string;
  model: string;
  simulated: boolean;
  reused: boolean;
}

export interface WorkerIntroductionFields {
  name: string | null;
  trade: string | null;
  years_experience: number | null;
  services_offered: string[];
  services_not_offered: string[];
}

export interface JobDescriptionFields {
  description: string | null;
  trade: string | null;
  services: string[];
  services_excluded: string[];
  area: string | null;
  preferred_time_text: string | null;
  budget_pkr: number | null;
}

export type DraftFields = Partial<WorkerIntroductionFields & JobDescriptionFields>;

export interface Draft {
  fields: DraftFields;
  missing: string[];
  uncertain: string[];
  unmatched_mentions: { phrase: string; negated: boolean }[];
  heard: Record<string, string>;
}

export interface Interpretation {
  id: string;
  kind: VoiceKind;
  language: string;
  source: { text: string; transcription_id: string | null };
  draft: Draft;
  corrections: DraftFields;
  effective_fields: DraftFields;
  confirmed: { fields: DraftFields; confirmed_at: string } | null;
  provider: string;
  model: string;
  simulated: boolean;
  reused: boolean;
}

export interface Synthesis {
  id: string;
  language: "ur" | "en";
  voice: string;
  provider: string;
  simulated: boolean;
  mime_type: string;
  size_bytes: number;
  content_url: string;
  reused: boolean;
}

export function uploadClip(file: Blob, filename: string, purpose: ClipPurpose, source: "recording" | "upload") {
  const form = new FormData();
  form.append("file", file, filename);
  form.append("purpose", purpose);
  form.append("source", source);
  return apiRequest<AudioClip>("/audio/clips/", { method: "POST", body: form, timeoutMs: 30_000 });
}

export const transcribe = (clipId: string, language: LanguageHint) =>
  apiRequest<Transcription>("/audio/transcribe/", {
    method: "POST",
    body: { clip_id: clipId, language },
    timeoutMs: AI_TIMEOUT_MS,
  });

export const interpretTranscription = (kind: VoiceKind, transcriptionId: string, language: string) =>
  apiRequest<Interpretation>("/interpretations/", {
    method: "POST",
    body: { kind, transcription_id: transcriptionId, language },
    timeoutMs: AI_TIMEOUT_MS,
  });

export const interpretText = (kind: VoiceKind, text: string, language: string) =>
  apiRequest<Interpretation>("/interpretations/", {
    method: "POST",
    body: { kind, text, language },
    timeoutMs: AI_TIMEOUT_MS,
  });

export const saveCorrections = (id: string, fields: DraftFields) =>
  apiRequest<Interpretation>(`/interpretations/${id}/`, { method: "PATCH", body: { fields } });

export const confirmInterpretation = (id: string) =>
  apiRequest<Interpretation>(`/interpretations/${id}/confirm/`, { method: "POST" });

export const synthesise = (text: string, language: "ur" | "en") =>
  apiRequest<Synthesis>("/audio/synthesise/", { method: "POST", body: { text, language }, timeoutMs: AI_TIMEOUT_MS });

/** Private audio is fetched with the session cookie and played from a blob URL. */
export const fetchPrivateAudio = (contentUrl: string) =>
  apiRequest<Blob>(contentUrl.replace(/^\/api\/v1/, ""), { responseType: "blob", timeoutMs: 30_000 });
