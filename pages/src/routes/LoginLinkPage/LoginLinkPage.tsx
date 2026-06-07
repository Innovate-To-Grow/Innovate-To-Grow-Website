import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router-dom';
import {loginLinkAutoLogin} from '@/features/auth';
import {dispatchAuthStateChange} from '@/features/auth/components/context/shared';
import {getPostAuthPath} from '@/features/auth/api/redirects';
import {getAccessToken} from '@/features/auth/api/storage';

function hasStoredAccessToken() {
  try {
    return Boolean(getAccessToken());
  } catch {
    return false;
  }
}

export function LoginLinkPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get('token'), [searchParams]);
  const [error, setError] = useState<string | null>(
    token ? null : 'No login token provided.',
  );

  useEffect(() => {
    if (!token) return;

    let cancelled = false;

    loginLinkAutoLogin(token)
      .then((response) => {
        if (!cancelled) {
          dispatchAuthStateChange();
          navigate(getPostAuthPath(response), {replace: true});
        }
      })
      .catch(() => {
        if (cancelled) return;
        // A one-time link fails when clicked again, but the first click usually
        // already signed this browser in — continue to the account page instead
        // of showing a dead end.
        if (hasStoredAccessToken()) {
          navigate('/account', {replace: true});
          return;
        }
        setError('This login link is invalid or has expired. Please log in manually.');
      });

    return () => {
      cancelled = true;
    };
  }, [token, navigate]);

  if (error) {
    return (
      <div className="magic-login-page">
        <p className="magic-login-error">{error}</p>
        <a href="/login" className="magic-login-link">Go to Login</a>
      </div>
    );
  }

  return (
    <div className="magic-login-page">
      <p>Signing you in...</p>
    </div>
  );
}
