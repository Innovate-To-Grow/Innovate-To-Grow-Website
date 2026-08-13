import { useEffect, useRef, useState } from 'react';
import {
  type CMSPageResponse,
  fetchCMSLivePreview,
  fetchCMSHomepage,
  fetchCMSPage,
  fetchCMSPreview,
  isCMSPageRedirectResponse,
} from '@/features/cms/api';

interface UseCMSPageResult {
  page: CMSPageResponse | null;
  redirectTo: string | null;
  loading: boolean;
  error: string | null;
  isLivePreview: boolean;
  retry: () => void;
}

interface CMSPageState {
  route: string;
  page: CMSPageResponse | null;
  redirectTo: string | null;
  error: string | null;
}

const LIVE_PREVIEW_POLL_MS = 1500;

export function useCMSPage(route: string, preview = false): UseCMSPageResult {
  const [state, setState] = useState<CMSPageState>({
    route: '',
    page: null,
    redirectTo: null,
    error: null,
  });
  const [requestVersion, setRequestVersion] = useState(0);

  const params = new URLSearchParams(window.location.search);
  const previewToken = params.get('cms_preview_token');
  const livePreviewId = params.get('cms_live_preview');
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Normal / token-preview fetch
  useEffect(() => {
    if (livePreviewId) return;

    let cancelled = false;
    const controller = new AbortController();

    const fetcher = previewToken
      ? fetchCMSPreview(previewToken)
      : route === '/' && !preview
        ? fetchCMSHomepage(controller.signal)
        : fetchCMSPage(route, preview, controller.signal);

    fetcher
      .then((data) => {
        if (cancelled) return;

        if (isCMSPageRedirectResponse(data)) {
          // Preview requests must never navigate away from the content being
          // reviewed, even if a malformed/stale backend response contains a
          // redirect payload.
          setState({
            route,
            page: null,
            redirectTo: preview || previewToken ? null : data.redirect_to,
            error: preview || previewToken ? 'error' : null,
          });
          return;
        }

        setState({ route, page: data, redirectTo: null, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          const status = err?.response?.status;
          setState({
            route,
            page: null,
            redirectTo: null,
            error: status === 404 ? 'not_found' : 'error',
          });
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [route, preview, previewToken, livePreviewId, requestVersion]);

  // Live preview: initial fetch + polling
  useEffect(() => {
    if (!livePreviewId) return;

    let cancelled = false;

    const doFetch = async () => {
      try {
        const data = await fetchCMSLivePreview(livePreviewId);
        if (!cancelled) {
          setState({ route, page: data, redirectTo: null, error: null });
        }
      } catch {
        // Keep showing whatever we already have; don't blank the page on transient errors
      } finally {
        // Schedule only after the current request settles, preventing an older
        // overlapping response from replacing a newer preview revision.
        if (!cancelled) {
          pollRef.current = setTimeout(doFetch, LIVE_PREVIEW_POLL_MS);
        }
      }
    };

    void doFetch();

    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [livePreviewId, route]);

  if (!livePreviewId && state.route !== route) {
    return {
      page: null,
      redirectTo: null,
      loading: true,
      error: null,
      isLivePreview: false,
      retry: () => setRequestVersion((value) => value + 1),
    };
  }

  return {
    page: state.page,
    redirectTo: state.redirectTo,
    loading: false,
    error: state.error,
    isLivePreview: !!livePreviewId,
    retry: () => setRequestVersion((value) => value + 1),
  };
}
