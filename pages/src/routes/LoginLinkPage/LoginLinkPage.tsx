import {useEffect, useState, useMemo} from 'react';
import {useSearchParams, useNavigate} from 'react-router';
import {
  bootstrapAuthSession,
  classifyLoginLinkFailure,
  getAccessToken,
  getPostAuthPath,
  loginLinkAutoLogin,
  type LoginLinkFailure,
} from '@/features/auth/api';
import {dispatchAuthStateChange} from '@/features/auth/components/context/shared';
import {
  clearAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';
import {LoginLinkFallback} from './LoginLinkFallback';

const NOT_SAVED_MESSAGE =
  'Your browser blocked saving your login session. Please log in manually.';

// No token to exchange: nothing to retry, and nothing to tell the visitor
// beyond "this link can't be used".
const UNUSABLE_LINK: LoginLinkFailure = {
  kind: 'invalid',
  retryable: false,
  redirectTo: null,
};

// Something threw after the exchange (or while leaving the page). The session
// may already be stored, so trying again is safe: a spent link is answered
// "already used", which continues to /account.
const UNEXPECTED_FAILURE: LoginLinkFailure = {
  kind: 'unavailable',
  retryable: true,
  redirectTo: null,
};

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
  const callbackParams = useMemo(
    () => readAuthCallbackParams('login-link', searchParams),
    [searchParams],
  );
  const token = callbackParams.get('token');
  const [failure, setFailure] = useState<LoginLinkFailure | null>(
    token ? null : UNUSABLE_LINK,
  );
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) {
      clearAuthCallbackParams('login-link');
      return;
    }

    let cancelled = false;

    // The sessionStorage handoff is the only copy of the token that survives a
    // reload, so it is dropped only once the outcome is final. A rate limit or
    // an unreachable server keeps it (its TTL bounds the exposure) so Retry —
    // or reloading the page — can try again with the same token. The fallback
    // drops it as soon as the visitor moves on to a code sign-in; Retry then
    // still works from the copy held in memory.
    const exchange = async () => {
      let response;
      try {
        response = await loginLinkAutoLogin(token);
      } catch (error) {
        const outcome = classifyLoginLinkFailure(error);
        if (!outcome.retryable) clearAuthCallbackParams('login-link');
        if (cancelled) return;

        // A one-time link fails when clicked again, but the first click usually
        // already signed this browser in — continue to the account page instead
        // of offering a sign-in the visitor no longer needs. Only a used link may
        // do this: every other failure gets the fallback, or a stale session
        // would hide it. Known trade-off: the stored session may belong to a
        // different member than the link's owner (shared browser); that is the
        // same outcome as visiting /account directly, and the failed token
        // reveals nothing about its owner.
        //
        // A stored session is not proof of a signed-in visitor, though: a dead
        // one is cleared by the provider's own check as soon as /account opens,
        // which would leave the visitor anonymous and without the link's
        // destination. So the session is checked first, through the same
        // (shared, de-duplicated) call the provider makes. Only a definitive
        // "not signed in" falls back to the code sign-in; a check that could not
        // reach a verdict keeps the session, as the provider does.
        if (outcome.kind === 'already_used' && hasStoredAccessToken()) {
          const session = await bootstrapAuthSession();
          if (cancelled) return;
          if (session.status !== 'anonymous') {
            navigate('/account', {replace: true});
            return;
          }
        }
        setFailure(outcome);
        return;
      }

      clearAuthCallbackParams('login-link');
      if (cancelled) return;
      dispatchAuthStateChange();
      navigate(getPostAuthPath(response), {replace: true});
    };

    // Nothing below may leave the page on "Signing you in...": a throw after
    // the exchange (or from a navigate) falls through to the fallback.
    void exchange().catch(() => {
      if (!cancelled) setFailure(UNEXPECTED_FAILURE);
    });

    return () => {
      cancelled = true;
    };
  }, [token, navigate, attempt]);

  // Retry is only rendered while no request is in flight: it clears the failure
  // (back to "Signing you in...") before the effect re-runs the exchange.
  const retry = () => {
    setFailure(null);
    setAttempt((count) => count + 1);
  };

  if (failure?.kind === 'session_not_saved') {
    // The token is spent and the browser could not keep the session, so the
    // email-code fallback could not persist one either: say so plainly.
    return (
      <div className="magic-login-page">
        <p className="magic-login-error">{NOT_SAVED_MESSAGE}</p>
        <a href="/login" className="magic-login-link">Go to Login</a>
      </div>
    );
  }

  if (failure) {
    return (
      <LoginLinkFallback
        kind={failure.kind}
        returnTo={failure.redirectTo}
        onRetry={failure.retryable ? retry : undefined}
      />
    );
  }

  return (
    <div className="magic-login-page">
      <p>Signing you in...</p>
    </div>
  );
}
