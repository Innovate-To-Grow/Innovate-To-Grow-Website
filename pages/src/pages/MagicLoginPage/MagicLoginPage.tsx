import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router-dom';
import {magicAutoLogin} from '../../services/auth';
import {dispatchAuthStateChange} from '../../components/Auth/context/shared';
import {getSafeInternalRedirectPath} from '../../shared/auth/redirects';

export function MagicLoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get('token'), [searchParams]);
  const [error, setError] = useState<string | null>(
    token ? null : 'No login token provided.',
  );

  useEffect(() => {
    if (!token) return;

    let cancelled = false;

    magicAutoLogin(token)
      .then((response) => {
        if (!cancelled) {
          dispatchAuthStateChange();
          navigate(getSafeInternalRedirectPath(response.redirect_to) ?? '/account', {replace: true});
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('This login link is invalid or has expired. Please log in manually.');
        }
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
