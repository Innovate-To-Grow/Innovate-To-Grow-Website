import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router-dom';
import {ticketAutoLogin} from '../../services/auth';
import {getPostAuthPath} from '../../shared/auth/redirects';

export function TicketLoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get('token'), [searchParams]);
  const [error, setError] = useState<string | null>(
    token ? null : 'No login token provided.',
  );

  useEffect(() => {
    if (!token) return;

    let cancelled = false;

    ticketAutoLogin(token)
      .then((response) => {
        if (!cancelled) {
          window.dispatchEvent(new Event('i2g-auth-state-change'));
          navigate(getPostAuthPath(response), {replace: true});
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
      <div className="ticket-login-page">
        <p className="ticket-login-error">{error}</p>
        <a href="/login" className="ticket-login-link">Go to Login</a>
      </div>
    );
  }

  return (
    <div className="ticket-login-page">
      <p>Signing you in...</p>
    </div>
  );
}
