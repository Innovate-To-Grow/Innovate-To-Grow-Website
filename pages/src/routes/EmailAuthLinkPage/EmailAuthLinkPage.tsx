import {useEffect, useMemo, useState} from 'react';
import {useNavigate, useSearchParams} from 'react-router-dom';
import {dispatchAuthStateChange, getAuthErrorMessage} from '../../components/Auth/context/shared';
import {consumeEmailAuthQuery, type EmailAuthFlow, type EmailAuthSource} from '../../services/auth';
import {getEmailAuthSourcePath} from '../../shared/auth/redirects';

const isEmailAuthFlow = (value: string | null): value is EmailAuthFlow =>
  value === 'auth' || value === 'login' || value === 'register';

const isEmailAuthSource = (value: string | null): value is EmailAuthSource =>
  value === 'login' || value === 'subscribe' || value === 'event_registration' || value === 'register';

export function EmailAuthLinkPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const flow = useMemo(() => searchParams.get('flow'), [searchParams]);
  const source = useMemo(() => searchParams.get('source'), [searchParams]);
  const email = useMemo(() => searchParams.get('email')?.trim().toLowerCase() ?? '', [searchParams]);
  const code = useMemo(() => searchParams.get('code')?.trim() ?? '', [searchParams]);
  const [error, setError] = useState<string | null>(
    isEmailAuthFlow(flow) && isEmailAuthSource(source) && email && /^\d{6}$/.test(code)
      ? null
      : 'This email link is invalid or incomplete.',
  );

  useEffect(() => {
    if (!isEmailAuthFlow(flow) || !isEmailAuthSource(source) || !email || !/^\d{6}$/.test(code)) {
      return;
    }

    let cancelled = false;

    consumeEmailAuthQuery({flow, email, code})
      .then((response) => {
        if (!cancelled) {
          dispatchAuthStateChange();
          navigate(getEmailAuthSourcePath(source, response), {replace: true});
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(getAuthErrorMessage(err));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [code, email, flow, navigate, source]);

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
      <p>Verifying your email...</p>
    </div>
  );
}
