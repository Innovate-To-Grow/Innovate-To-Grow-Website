import {useEffect, useMemo, useState} from 'react';
import {useNavigate, useSearchParams} from 'react-router';
import {dispatchAuthStateChange, getAuthErrorMessage} from '@/features/auth/components/context/shared';
import {consumeEmailAuthQuery, type EmailAuthFlow, type EmailAuthSource} from '@/features/auth';
import {getEmailAuthSourcePath} from '@/features/auth/api/redirects';
import {
  clearAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';

const isEmailAuthFlow = (value: string | null): value is EmailAuthFlow =>
  value === 'auth' || value === 'login' || value === 'register';

const isEmailAuthSource = (value: string | null): value is EmailAuthSource =>
  value === 'login' || value === 'subscribe' || value === 'event_registration' || value === 'register';

export function EmailAuthLinkPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const callbackParams = useMemo(
    () => readAuthCallbackParams('email-auth-link', searchParams),
    [searchParams],
  );
  const flow = callbackParams.get('flow');
  const source = callbackParams.get('source');
  const email = callbackParams.get('email')?.trim().toLowerCase() ?? '';
  const code = callbackParams.get('code')?.trim() ?? '';
  const eventSlug = callbackParams.get('event');
  const [error, setError] = useState<string | null>(
    isEmailAuthFlow(flow) && isEmailAuthSource(source) && email && /^\d{6}$/.test(code)
      ? null
      : 'This email link is invalid or incomplete.',
  );

  useEffect(() => {
    clearAuthCallbackParams('email-auth-link');
    if (!isEmailAuthFlow(flow) || !isEmailAuthSource(source) || !email || !/^\d{6}$/.test(code)) {
      return;
    }

    let cancelled = false;

    consumeEmailAuthQuery({flow, email, code})
      .then((response) => {
        if (!cancelled) {
          dispatchAuthStateChange();
          navigate(getEmailAuthSourcePath(source, response, eventSlug), {replace: true});
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
  }, [code, email, eventSlug, flow, navigate, source]);

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
