import '@/features/auth/components/shared/linkLandingPages.css';
import {useEffect, useMemo, useState} from 'react';
import {useNavigate, useParams} from 'react-router';
import {
  buildLoginPath,
  classifyLoginLinkFailure,
  getPostAuthPath,
  getSafeInternalRedirectPath,
  openSmsLink,
  type LoginLinkFailure,
} from '@/features/auth/api';
import {clearAuthCallbackParams, readAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {dispatchAuthStateChange} from '@/features/auth/components/context/shared';

const NOTICES: Record<LoginLinkFailure['kind'], string> = {
  expired: 'This link has expired.',
  already_used: 'This link has already been used.',
  invalid: "This link can't be used.",
  rate_limited: "We couldn't open your link right now.",
  unavailable: "We couldn't open your link right now.",
  session_not_saved: 'Your browser blocked saving your sign-in. Please sign in instead.',
};

// No token to exchange: nothing to retry.
const UNUSABLE_LINK: LoginLinkFailure = {kind: 'invalid', retryable: false, redirectTo: null};
// Something threw after the exchange: trying again is safe (a spent link then answers "already used").
const UNEXPECTED_FAILURE: LoginLinkFailure = {kind: 'unavailable', retryable: true, redirectTo: null};

/**
 * The token of the SMS link this page opens: moved out of the address at
 * start-up (`captureAuthCallbackParams`), or still in it when the page was
 * reached inside the app (`/l/:token`).
 */
function readToken(pathToken: string | undefined): string | null {
  return readAuthCallbackParams('sms-link', new URLSearchParams()).get('token') ?? pathToken ?? null;
}

interface FallbackProps {
  failure: LoginLinkFailure;
  onRetry?: () => void;
}

/** A link that cannot be used: say why, and offer the sign-in page (email or phone), returning to the link's page. */
function SmsLinkFallback({failure, onRetry}: FallbackProps) {
  return (
    <div className="magic-login-page">
      <p className="itg-notice magic-login-error" role="status" id="sms-link-notice">
        {NOTICES[failure.kind]} You can sign in with your email address or phone number instead.
      </p>
      <a href={buildLoginPath(failure.redirectTo)} className="itg-btn itg-btn-primary magic-login-link">
        Sign in
      </a>
      {onRetry && (
        <button type="button" className="itg-btn itg-btn-text" onClick={onRetry}>
          Try the link again
        </button>
      )}
    </div>
  );
}

/** `/l/<token>`: an SMS short link. A personal one signs its member in once; any other one opens its page. */
export function SmsLinkPage() {
  const {token: pathToken} = useParams<{token?: string}>();
  const navigate = useNavigate();
  const token = useMemo(() => readToken(pathToken), [pathToken]);
  const [failure, setFailure] = useState<LoginLinkFailure | null>(token ? null : UNUSABLE_LINK);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // The server's answer is the only authority: the token itself signs no one in.
    if (!token) return;
    let cancelled = false;
    const exchange = async () => {
      let result;
      try {
        result = await openSmsLink(token);
      } catch (error) {
        const outcome = classifyLoginLinkFailure(error);
        if (!outcome.retryable) clearAuthCallbackParams('sms-link');
        if (!cancelled) setFailure(outcome);
        return;
      }
      clearAuthCallbackParams('sms-link');
      if (cancelled) return;
      if (result.kind === 'sign_in') {
        dispatchAuthStateChange();
        navigate(getPostAuthPath(result.login), {replace: true});
        return;
      }
      navigate(getSafeInternalRedirectPath(result.redirectTo) ?? '/', {replace: true});
    };
    void exchange().catch(() => {
      if (!cancelled) setFailure(UNEXPECTED_FAILURE);
    });
    return () => {
      cancelled = true;
    };
  }, [token, navigate, attempt]);

  if (failure) {
    const retry = () => {
      setFailure(null);
      setAttempt((count) => count + 1);
    };
    return <SmsLinkFallback failure={failure} onRetry={failure.retryable ? retry : undefined} />;
  }

  return (
    <div className="magic-login-page">
      <p className="magic-login-status" role="status">Opening your link...</p>
    </div>
  );
}
