import api from './client';

export interface SheetRow {
  Track: string;
  Order: string;
  'Year-Semester': string;
  Class: string;
  'Team#': string;
  TeamName: string;
  'Project Title': string;
  Organization: string;
  Industry: string;
  Abstract: string;
  'Student Names': string;
  NameTitle: string;
}

export interface TrackInfo {
  name: string;
  room: string;
  zoomLink: string;
}

export interface SheetsDataResponse {
  slug: string;
  title: string;
  sheet_type: string;
  rows: SheetRow[];
  track_infos: TrackInfo[];
}

const sheetsCache: Record<string, Promise<SheetsDataResponse>> = {};

/**
 * Fetch sheet data from the backend API by slug.
 * Results are cached per-slug so multiple callers sharing the same slug
 * reuse the same in-flight or resolved promise.
 */
export function fetchSheetsData(slug: string): Promise<SheetsDataResponse> {
  const cached = sheetsCache[slug];
  if (cached) {
    return cached;
  }

  const promise = api.get<SheetsDataResponse>(`/sheets/${slug}/`).then(
    response => response.data,
    error => {
      delete sheetsCache[slug];
      throw error;
    },
  );
  sheetsCache[slug] = promise;
  return promise;
}

export const clearSheetsCache = (slug?: string) => {
  if (slug) {
    delete sheetsCache[slug];
  } else {
    for (const key of Object.keys(sheetsCache)) {
      delete sheetsCache[key];
    }
  }
};
