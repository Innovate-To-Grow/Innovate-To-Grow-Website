import { useEffect, useState } from 'react';
import {
  type CMSPageResponse,
  fetchCMSPage,
  fetchCMSPreview,
} from '../../services/api/cms';

interface UseCMSPageResult {
  page: CMSPageResponse | null;
  loading: boolean;
  error: string | null;
}

interface CMSPageState {
  route: string;
  page: CMSPageResponse | null;
  error: string | null;
}

export function useCMSPage(route: string, preview = false): UseCMSPageResult {
  const [state, setState] = useState<CMSPageState>({
    route: '',
    page: null,
    error: null,
  });

  // Check for preview token in URL
  const previewToken = new URLSearchParams(window.location.search).get(
    'cms_preview_token',
  );

  useEffect(() => {
    let cancelled = false;

    const fetcher = previewToken
      ? fetchCMSPreview(previewToken)
      : fetchCMSPage(route, preview);

    fetcher
      .then((data) => {
        if (!cancelled) {
          setState({
            route,
            page: data,
            error: null,
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const status = err?.response?.status;
          setState({
            route,
            page: null,
            error: status === 404 ? 'not_found' : 'error',
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [route, preview, previewToken]);

  if (state.route !== route) {
    return { page: null, loading: true, error: null };
  }

  return { page: state.page, loading: false, error: state.error };
}
