import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router-dom';
import {impersonateAutoLogin} from '../../shared/auth/session';
import {dispatchAuthStateChange} from '../../components/Auth/context/shared';
import {getPostAuthPath} from '../../shared/auth/redirects';

export function ImpersonateLoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get('token'), [searchParams]);
  const [error, setError] = useState<string | null>(
    token ? null : 'No impersonation token provided.',
  );

  useEffect(() => {
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
