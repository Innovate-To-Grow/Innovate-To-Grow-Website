import { useEffect, useState } from 'react';
import { type CMSPageResponse, fetchCMSPage } from '../../services/api/cms';

interface UseCMSPageResult {
  page: CMSPageResponse | null;
  loading: boolean;
  error: string | null;
}

export function useCMSPage(route: string, preview = false): UseCMSPageResult {
  const [page, setPage] = useState<CMSPageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchCMSPage(route, preview)
      .then((data) => {
        if (!cancelled) {
          setPage(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const status = err?.response?.status;
          setError(status === 404 ? 'not_found' : 'error');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [route, preview]);

  return { page, loading, error };
}
