import {useEffect, useState} from 'react';
import {deleteShare, listMyShares, type PastProjectShareSummary} from '@/features/projects/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

export const useMySharedLinks = (enabled = true, surfaceLoadError = false) => {
  const [shares, setShares] = useState<PastProjectShareSummary[]>([]);
  const [fetchLoading, setFetchLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Derive the exposed loading flag instead of syncing it from the effect: when
  // the hook is disabled there is no fetch in flight, so it is never loading.
  const loading = enabled && fetchLoading;

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let active = true;
    // Reset state inside the async flow so the effect body holds no synchronous
    // setState. These run before the first await, so timing/ordering is unchanged:
    // a refetch shows the loading indicator and clears any stale error first.
    (async () => {
      setFetchLoading(true);
      setError(null);
      try {
        const data = await listMyShares();
        if (active) setShares(data);
      } catch (err) {
        // A failed load just leaves the section hidden; surfacing an error on an
        // account page the user may never have used would be noise.
        console.error('[MySharedLinks] failed to load shares', err);
        if (active && surfaceLoadError) setError(getAuthApiErrorMessage(err));
      } finally {
        if (active) setFetchLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [enabled, surfaceLoadError]);

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this shared link? Anyone with the URL will lose access.')) {
      return;
    }
    setError(null);
    setSuccessMessage(null);
    try {
      await deleteShare(id);
      setShares((current) => current.filter((share) => share.id !== id));
      setSuccessMessage('Shared link deleted.');
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  return {shares, loading, error, successMessage, handleDelete};
};
