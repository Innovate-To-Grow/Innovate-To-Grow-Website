import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router-dom';
import {unsubscribeAutoLogin} from '../../services/auth';

export function UnsubscribeLoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get('token'), [searchParams]);
  const [error, setError] = useState<string | null>(
    token ? null : 'No login token provided.',
  );

  useEffect(() => {
    if (!token) return;

    let cancelled = false;

    unsubscribeAutoLogin(token)
      .then(() => {
        if (!cancelled) {
          window.dispatchEvent(new Event('i2g-auth-state-change'));
          navigate('/account', {replace: true});
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
      <div className="unsubscribe-login-page">
        <p className="unsubscribe-login-error">{error}</p>
        <a href="/login" className="unsubscribe-login-link">Go to Login</a>
      </div>
    );
  }

  return (
    <div className="unsubscribe-login-page">
      <p>Signing you in...</p>
    </div>
  );
}
