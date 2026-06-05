import {useEffect, useState} from 'react';
import {deleteShare, listMyShares, type PastProjectShareSummary} from '@/features/projects/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

export const useMySharedLinks = () => {
  const [shares, setShares] = useState<PastProjectShareSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await listMyShares();
        if (active) setShares(data);
      } catch (err) {
        // A failed load just leaves the section hidden; surfacing an error on an
        // account page the user may never have used would be noise.
        console.error('[MySharedLinks] failed to load shares', err);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

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

  const handleCopy = async (shareUrl: string) => {
    setError(null);
    setSuccessMessage(null);
    try {
      await navigator.clipboard.writeText(shareUrl);
      setSuccessMessage('Link copied to clipboard.');
    } catch {
      setError('Unable to copy the link. Please copy it manually.');
    }
  };

  return {shares, loading, error, successMessage, handleDelete, handleCopy};
};
