import { api } from '@/lib/api';
import {
  type CMSEmbedResponse,
  type CMSKnownBlock,
  type CMSPageRedirectResponse,
  type CMSPageResponse,
} from './types';
import {getWithOneRetry} from './retry';
import {normalizeCMSRoute} from './routes';

export type CMSKnownBlockType = CMSKnownBlock['block_type'];

export type CMSPageFetchResponse = CMSPageResponse | CMSPageRedirectResponse;

export function isCMSPageRedirectResponse(
  response: CMSPageFetchResponse,
): response is CMSPageRedirectResponse {
  return (
    'redirect_to' in response
    && typeof response.redirect_to === 'string'
    && response.permanent === true
  );
}

export async function fetchCMSPage(
  route: string,
  preview = false,
  signal?: AbortSignal,
): Promise<CMSPageFetchResponse> {
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
  return getWithOneRetry<CMSPageFetchResponse>(url, {signal});
}

let homepageRequest: {
  controller: AbortController;
  promise: Promise<CMSPageFetchResponse>;
  consumers: number;
} | null = null;

export function fetchCMSHomepage(signal?: AbortSignal): Promise<CMSPageFetchResponse> {
  if (!homepageRequest) {
    const controller = new AbortController();
    const request = {
      controller,
      consumers: 0,
      promise: getWithOneRetry<CMSPageFetchResponse>('/cms/homepage/', {signal: controller.signal})
      .finally(() => {
        if (homepageRequest === request) homepageRequest = null;
      }),
    };
    homepageRequest = request;
  }

  const request = homepageRequest;
  request.consumers += 1;
  let released = false;
  const release = () => {
    if (released) return;
    released = true;
    request.consumers -= 1;
    queueMicrotask(() => {
      if (request.consumers === 0 && homepageRequest === request) {
        request.controller.abort();
      }
    });
  };

  if (signal?.aborted) {
    release();
    return Promise.reject(new DOMException('The request was aborted.', 'AbortError'));
  }
  signal?.addEventListener('abort', release, {once: true});
  return request.promise.finally(() => {
    signal?.removeEventListener('abort', release);
    release();
  });
}

export async function fetchCMSPreview(
  token: string,
): Promise<CMSPageResponse> {
  const response = await api.get<CMSPageResponse>(
    `/cms/preview/${encodeURIComponent(token)}/`,
  );
  return response.data;
}

export async function fetchCMSLivePreview(
  pageId: string,
): Promise<CMSPageResponse> {
  const response = await api.get<CMSPageResponse>(
    `/cms/live-preview/${encodeURIComponent(pageId)}/`,
  );
  return response.data;
}

// The embed-host allowlist is read by the shared HTML sanitizer, so it lives in lib/api.
export {fetchCMSEmbedHosts, type CMSEmbedHostsResponse} from '@/lib/api/embedHosts';

export async function fetchCMSEmbed(
  embedSlug: string,
): Promise<CMSEmbedResponse> {
  const response = await api.get<CMSEmbedResponse>(`/cms/embed/${embedSlug}/`);
  return response.data;
}

// Re-exported so '@/features/cms/api' keeps its public surface.
export type {CMSBlock, CMSEmbedResponse, CMSEmbedWidgetType, CMSKnownBlock, CMSPageRedirectResponse, CMSPageResponse, CMSUnknownBlock} from './types';
export {normalizeCMSRoute} from './routes';
