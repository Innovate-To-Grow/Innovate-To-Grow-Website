import { api } from '../../shared/api/client';

const CMS_ROUTE_SEGMENT_RE = /^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$/;
const URL_SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]*:/;

export interface CMSBlock {
  block_type: string;
  sort_order: number;
  data: Record<string, unknown>;
}

export interface CMSPageResponse {
  slug: string;
  route: string;
  title: string;
  page_css_class: string;
  page_css: string;
  meta_description: string;
  blocks: CMSBlock[];
  expires_at?: string;
}

export function normalizeCMSRoute(route: string): string {
  const trimmed = route.trim();
  if (
    !trimmed ||
    trimmed === '/' ||
    URL_SCHEME_RE.test(trimmed) ||
    trimmed.startsWith('//') ||
    trimmed.includes('\\')
  ) {
    return '/';
  }

  const segments = trimmed.split('/').filter(Boolean);
  if (!segments.every((segment) => CMS_ROUTE_SEGMENT_RE.test(segment))) {
    return '/';
  }
  return segments.length > 0 ? `/${segments.join('/')}` : '/';
}

export async function fetchCMSPage(
  route: string,
  preview = false,
): Promise<CMSPageResponse> {
  const normalizedRoute = normalizeCMSRoute(route);
  const path = normalizedRoute
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  const params = new URLSearchParams();
  if (preview) params.set('preview', 'true');
  const qs = params.toString();
  const url = `/cms/pages/${path}${path ? '/' : ''}${qs ? `?${qs}` : ''}`;
  const response = await api.get<CMSPageResponse>(url);
  return response.data;
}

export async function fetchCMSPreview(
  token: string,
): Promise<CMSPageResponse> {
  const response = await api.get<CMSPageResponse>(`/cms/preview/${token}/`);
  return response.data;
}

export async function fetchCMSLivePreview(
  pageId: string,
): Promise<CMSPageResponse> {
  const response = await api.get<CMSPageResponse>(`/cms/live-preview/${pageId}/`);
  return response.data;
}

export type CMSEmbedWidgetType = 'blocks' | 'app_route';

export interface CMSEmbedResponse {
  widget_type?: CMSEmbedWidgetType;
  app_route?: string;
  blocks: CMSBlock[];
  page_css_class: string;
  page_css: string;
  hide_section_titles?: boolean;
}

export async function fetchCMSEmbed(
  embedSlug: string,
): Promise<CMSEmbedResponse> {
  const response = await api.get<CMSEmbedResponse>(`/cms/embed/${embedSlug}/`);
  return response.data;
}
