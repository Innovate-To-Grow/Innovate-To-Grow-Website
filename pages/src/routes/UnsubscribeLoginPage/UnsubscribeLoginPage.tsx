import {useEffect, useMemo, useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {unsubscribeAutoLogin} from '@/features/auth';

export function UnsubscribeLoginPage() {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get('token'), [searchParams]);
  const [error, setError] = useState<string | null>(
    token ? null : 'No unsubscribe token provided.',
  );
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;

    unsubscribeAutoLogin(token)
      .then(() => {
        if (!cancelled) {
          setSuccess(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('This unsubscribe link is invalid or has expired. Please update your email preferences manually.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (error) {
    return (
      <div className="unsubscribe-login-page">
        <p className="unsubscribe-login-error">{error}</p>
        <a href="/account" className="unsubscribe-login-link">Manage email preferences</a>
      </div>
    );
  }

  if (success) {
    return (
      <div className="unsubscribe-login-page">
        <p>You have been unsubscribed from updates and announcements.</p>
        <a href="/account" className="unsubscribe-login-link">Manage email preferences</a>
      </div>
    );
  }

  return (
    <div className="unsubscribe-login-page">
      <p>Unsubscribing you...</p>
    </div>
  );
}
