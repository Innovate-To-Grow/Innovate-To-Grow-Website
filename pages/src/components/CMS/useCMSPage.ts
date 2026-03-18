import { useEffect, useRef, useState } from 'react';
import {
  type CMSPageResponse,
  fetchCMSLivePreview,
  fetchCMSPage,
  fetchCMSPreview,
} from '../../services/api/cms';

interface UseCMSPageResult {
  page: CMSPageResponse | null;
  loading: boolean;
  error: string | null;
  isLivePreview: boolean;
}

interface CMSPageState {
  route: string;
  page: CMSPageResponse | null;
  error: string | null;
}

const LIVE_PREVIEW_POLL_MS = 1500;

export function useCMSPage(route: string, preview = false): UseCMSPageResult {
  const [state, setState] = useState<CMSPageState>({
    route: '',
    page: null,
    error: null,
  });

  const params = new URLSearchParams(window.location.search);
  const previewToken = params.get('cms_preview_token');
  const livePreviewId = params.get('cms_live_preview');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Normal / token-preview fetch
  useEffect(() => {
    if (livePreviewId) return;

    let cancelled = false;

    const fetcher = previewToken
      ? fetchCMSPreview(previewToken)
      : fetchCMSPage(route, preview);

    fetcher
      .then((data) => {
        if (!cancelled) {
          setState({ route, page: data, error: null });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const status = err?.response?.status;
          setState({ route, page: null, error: status === 404 ? 'not_found' : 'error' });
        }
      });

    return () => { cancelled = true; };
  }, [route, preview, previewToken, livePreviewId]);

  // Live preview: initial fetch + polling
  useEffect(() => {
    if (!livePreviewId) return;

    let cancelled = false;

    const doFetch = () => {
      fetchCMSLivePreview(livePreviewId)
        .then((data) => {
          if (!cancelled) {
            setState({ route, page: data, error: null });
          }
        })
        .catch(() => {
          // Keep showing whatever we already have; don't blank the page on transient errors
        });
    };

    doFetch();
    pollRef.current = setInterval(doFetch, LIVE_PREVIEW_POLL_MS);

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [livePreviewId, route]);

  if (!livePreviewId && state.route !== route) {
    return { page: null, loading: true, error: null, isLivePreview: false };
  }

  return {
    page: state.page,
    loading: false,
    error: state.error,
    isLivePreview: !!livePreviewId,
  };
}
