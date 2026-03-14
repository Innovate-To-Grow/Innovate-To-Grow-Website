import { useEffect, useRef, useState } from 'react';
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

export function useCMSPage(route: string, preview = false): UseCMSPageResult {
  const [page, setPage] = useState<CMSPageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentRoute = useRef(route);

  // Check for preview token in URL
  const previewToken = new URLSearchParams(window.location.search).get(
    'cms_preview_token',
  );

  useEffect(() => {
    let cancelled = false;
    currentRoute.current = route;

    const fetcher = previewToken
      ? fetchCMSPreview(previewToken)
      : fetchCMSPage(route, preview);

    fetcher
      .then((data) => {
        if (!cancelled) {
          setPage(data);
          setLoading(false);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const status = err?.response?.status;
          setError(status === 404 ? 'not_found' : 'error');
          setPage(null);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [route, preview, previewToken]);

  return { page, loading, error };
}
