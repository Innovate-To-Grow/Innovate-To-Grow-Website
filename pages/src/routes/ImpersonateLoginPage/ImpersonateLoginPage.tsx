import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router';
import {impersonateAutoLogin} from '@/features/auth/api/session';
import {dispatchAuthStateChange} from '@/features/auth/components/context/shared';
import {getPostAuthPath} from '@/features/auth/api/redirects';
import {
  clearAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';

export function ImpersonateLoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const callbackParams = useMemo(
    () => readAuthCallbackParams('impersonate-login', searchParams),
    [searchParams],
  );
  const token = callbackParams.get('token');
  const [error, setError] = useState<string | null>(
    token ? null : 'No impersonation token provided.',
  );

  useEffect(() => {
    clearAuthCallbackParams('impersonate-login');
    if (!token) return;

    let cancelled = false;

    impersonateAutoLogin(token)
      .then((response) => {
        if (!cancelled) {
          dispatchAuthStateChange();
          navigate(getPostAuthPath(response), {replace: true});
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('This impersonation link is invalid or has expired.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, navigate]);

  if (error) {
    return (
      <div className="impersonate-login-page">
        <p className="impersonate-login-error">{error}</p>
        <a href="/login" className="impersonate-login-link">Go to Login</a>
      </div>
    );
  }

  return (
    <div className="impersonate-login-page">
      <p>Signing you in...</p>
    </div>
  );
}
