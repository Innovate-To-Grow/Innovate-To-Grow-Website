import { api } from '../../shared/api/client';

export interface MiniAppRecord {
  id: string;
  data: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface MiniAppPaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: MiniAppRecord[];
}

export async function fetchMiniAppCode(slug: string, path?: string): Promise<string> {
  const params = path ? { path } : undefined;
  const response = await api.get(`/miniapps/${slug}/code/`, { responseType: 'text', params });
  return response.data;
}

export async function fetchMiniAppSchema(slug: string): Promise<{ fields: unknown[] }> {
  const response = await api.get(`/miniapps/${slug}/schema/`);
  return response.data;
}

export async function listMiniAppRecords(
  slug: string,
  params?: Record<string, string>
): Promise<MiniAppPaginatedResponse> {
  const response = await api.get(`/miniapps/${slug}/data/`, { params });
  return response.data;
}

export async function getMiniAppRecord(slug: string, recordId: string): Promise<MiniAppRecord> {
  const response = await api.get(`/miniapps/${slug}/data/${recordId}/`);
  return response.data;
}

export async function createMiniAppRecord(
  slug: string,
  data: Record<string, unknown>
): Promise<MiniAppRecord> {
  const response = await api.post(`/miniapps/${slug}/data/`, { data });
  return response.data;
}

export async function updateMiniAppRecord(
  slug: string,
  recordId: string,
  data: Record<string, unknown>
): Promise<MiniAppRecord> {
  const response = await api.patch(`/miniapps/${slug}/data/${recordId}/`, { data });
  return response.data;
}

export async function deleteMiniAppRecord(slug: string, recordId: string): Promise<void> {
  await api.delete(`/miniapps/${slug}/data/${recordId}/`);
}
