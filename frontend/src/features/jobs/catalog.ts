import * as catalogApi from "../../api/catalog";
import type { Language } from "../../i18n/types";

export interface JobCatalog {
  trades: catalogApi.Trade[];
  services: catalogApi.ServiceTag[];
  areas: catalogApi.Area[];
}

export async function loadJobCatalog(signal?: AbortSignal): Promise<JobCatalog> {
  const [trades, services, areas] = await Promise.all([
    catalogApi.fetchTrades(signal),
    catalogApi.fetchAllServiceTags(signal),
    catalogApi.fetchAreas(signal),
  ]);
  return { trades: trades.results, services: services.results, areas: areas.results };
}

const pick = (labels: catalogApi.Labels, language: Language) => labels[language] || labels.en;

/** Label lookups that fall back to the code, so a deactivated entry still shows something. */
export function labeller(catalog: JobCatalog, language: Language) {
  return {
    trade: (code: string | null) => {
      const found = catalog.trades.find((item) => item.code === code);
      return found ? pick(found.labels, language) : (code ?? "");
    },
    service: (code: string) => {
      const found = catalog.services.find((item) => item.code === code);
      return found ? pick(found.labels, language) : code;
    },
    area: (code: string | null) => {
      const found = catalog.areas.find((item) => item.code === code);
      return found ? pick(found.labels, language) : (code ?? "");
    },
    city: (code: string | null) => {
      const found = catalog.areas.find((item) => item.city.code === code)?.city;
      return found ? pick(found.labels, language) : (code ?? "");
    },
  };
}

export function citiesOf(catalog: JobCatalog): catalogApi.City[] {
  const seen = new Map<string, catalogApi.City>();
  for (const area of catalog.areas) if (!seen.has(area.city.code)) seen.set(area.city.code, area.city);
  return [...seen.values()].sort((a, b) => a.sort_order - b.sort_order);
}
