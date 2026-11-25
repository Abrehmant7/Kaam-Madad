import { apiRequest } from "./client";

export interface Labels {
  ur: string;
  en: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Trade {
  code: string;
  labels: Labels;
  icon: string;
  sort_order: number;
  service_count: number;
}

export interface ServiceTag {
  code: string;
  trade: string;
  labels: Labels;
  icon: string;
  sort_order: number;
}

export interface City {
  code: string;
  labels: Labels;
  sort_order: number;
}

export interface Area {
  code: string;
  city: City;
  labels: Labels;
  kind: "sector" | "locality";
  centre: { latitude: number; longitude: number; approximate: true } | null;
  sort_order: number;
}

export interface SpecialityQuestion {
  code: "services_offered" | "primary_specialities" | "services_not_offered" | string;
  prompt: Labels;
  help: Labels;
  selection: { multiple: boolean; min: number; max: number | null; choices_from: "trade_services" | "services_offered" };
}

export interface SpecialityQuestionSet {
  trade: Trade;
  questions: SpecialityQuestion[];
  choices: ServiceTag[];
  rules: Array<Record<string, unknown>>;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const fetchTrades = (signal?: AbortSignal) =>
  apiRequest<Page<Trade>>(`/catalog/trades/${query({ page_size: 200 })}`, { signal });

export const fetchServiceTags = (trade: string, signal?: AbortSignal) =>
  apiRequest<Page<ServiceTag>>(`/catalog/service-tags/${query({ trade, page_size: 200 })}`, { signal });

/** Every active service (≤ 200), e.g. for the draft editor. */
export const fetchAllServiceTags = (signal?: AbortSignal) =>
  apiRequest<Page<ServiceTag>>(`/catalog/service-tags/${query({ page_size: 200 })}`, { signal });

export const fetchAreas = (signal?: AbortSignal) =>
  apiRequest<Page<Area>>(`/catalog/areas/${query({ page_size: 200 })}`, { signal });

export const fetchSpecialityQuestions = (trade: string, signal?: AbortSignal) =>
  apiRequest<SpecialityQuestionSet>(`/catalog/trades/${encodeURIComponent(trade)}/speciality-questions/`, { signal });
