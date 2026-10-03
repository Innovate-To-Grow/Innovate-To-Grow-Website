import {useEffect, useRef, useState, type FormEvent} from 'react';

import {Icon} from '@/components/Icon/Icon';
import {ResponsiveBrandImage} from '@/components/ResponsiveBrandImage';
import {useAuth} from '@/features/auth';
import type {LoginLinkFailureKind} from '@/features/auth/api';
import {clearAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {isSafeMessage} from '@/features/auth/components/context/shared';
import {VerifyEmailPageContent} from '@/features/auth/components/pages/VerifyEmailPage';
import {identifyLoginInput} from '@/features/auth/components/sections/internal/identifyLoginInput';
import {PrivacyLegalNotice} from '@/features/auth/components/shared/PrivacyLegalNotice';

/** Every failure that is shown here; a session the browser could not store is not. */
export type LoginLinkFallbackKind = Exclude<LoginLinkFailureKind, 'session_not_saved'>;

const RETRYABLE_NOTICE = "We couldn't verify your sign-in link right now.";

const NOTICES: Record<LoginLinkFallbackKind, string> = {
  expired: 'This sign-in link has expired.',
  already_used: 'This sign-in link has already been used.',
  rate_limited: RETRYABLE_NOTICE,
  unavailable: RETRYABLE_NOTICE,
  invalid: "This sign-in link can't be used.",
};

const INSTEAD =
  "Enter your email and we'll send you a 6-digit code to sign in instead.";

// Shown under the code field: the acknowledgement above it is deliberately the
// same for every address, so this is the only nudge a mistyped one gets.
const CODE_STEP_HINT = "Didn't get a code? Check the address above or go back to correct it.";

/**
 * The server's acknowledgement of a code request, if it sent a usable one. It is
 * shown as it came (for the login flow it is the same generic sentence for every
 * address), never replaced by wording of ours that could say more.
 */
function readAcknowledgement(response: unknown): string | null {
  const message = (response as {message?: unknown} | null | undefined)?.message;
  return typeof message === 'string' && message.trim() && isSafeMessage(message) ? message : null;
}

interface LoginLinkFallbackProps {
  kind: LoginLinkFallbackKind;
  /** Safe internal path the link was meant to open; where a code sign-in lands. */
  returnTo: string | null;
  /** Re-run the link exchange. Only given when trying the same link again can help. */
  onRetry?: () => void;
}

/**
 * What a visitor sees when an emailed sign-in link cannot be used: a plain
 * notice (not an error) and an email-code sign-in inline on the same route.
 *
 * It must stay inline. `/login` and `/verify-email` send an already
 * authenticated browser on to `/account`, which would strand exactly the
 * browser this page exists for (one holding another member's session). Signing
 * in with the code replaces that stored session.
 *
 * It uses the `login` code flow, which only ever issues a code to an existing,
 * active member and answers every other address with the same generic message.
 * A sign-in link exists only for an existing member, so a mistyped address must
 * not go through the unified email-auth flow, which would create a pending
 * account for it and sign the visitor in as that stranger. The step therefore
 * always advances once the request is accepted, whatever the address: it must
 * not reveal whether an account exists. The code step opens with the server's
 * own acknowledgement (the same generic sentence for every address) and a hint
 * for a mistyped address.
 */
export function LoginLinkFallback({kind, returnTo, onRetry}: LoginLinkFallbackProps) {
  const {requestLoginCode, error, isLoading, clearError} = useAuth();
  const emailInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState('');
  const [codeEmail, setCodeEmail] = useState('');
  const [codeMessage, setCodeMessage] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // An error left over from an earlier attempt belongs to that attempt.
  useEffect(() => {
    clearError();
  }, [clearError]);

  useEffect(() => {
    if (step === 'email') emailInputRef.current?.focus();
  }, [step]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (isLoading) return;
    clearError();

    const parsed = identifyLoginInput(email);
    // This sign-in is email-only, so a phone number is as invalid as text.
    if (parsed.type !== 'email') {
      setValidationError(
        email.trim()
          ? 'Please enter a valid email address.'
          : 'Please enter your email address.',
      );
      return;
    }
    setValidationError(null);

    // The code step verifies against the lowercased address, so the request
    // uses the same one.
    const normalized = parsed.value.toLowerCase();
    try {
      const response = await requestLoginCode(normalized);
      // The visitor is past the link now (Retry and Back use the token held in
      // memory). Keeping the sessionStorage copy would let a later bare
      // /login-link in this tab re-submit it and swap the session they are
      // about to sign in with.
      clearAuthCallbackParams('login-link');
      setCodeEmail(normalized);
      setCodeMessage(readAcknowledgement(response));
      setStep('code');
    } catch {
      // The auth context already exposes the failure as `error`.
    }
  };

  const handleBack = () => {
    clearError();
    setValidationError(null);
    setStep('email');
  };

  if (step === 'code') {
    return (
      <VerifyEmailPageContent
        flow="login"
        email={codeEmail}
        returnTo={returnTo}
        onBack={handleBack}
        onSignedIn={() => clearAuthCallbackParams('login-link')}
        autoFocus
        initialMessage={codeMessage}
        hint={CODE_STEP_HINT}
      />
    );
  }

  const message = validationError ?? error;

  return (
    <div className="auth-page">
      <div className="auth-page-card">
        <div className="auth-page-header">
          <ResponsiveBrandImage brand="i2g" alt="I2G" className="auth-page-logo" sizes="160px" />
          <h1 className="auth-page-title">Sign in to I2G</h1>
        </div>

        <div className="auth-alert-wrapper">
          <div className="auth-alert info" role="status">
            <Icon name="info-circle" className="auth-alert-icon" />
            <span id="login-link-fallback-notice">{`${NOTICES[kind]} ${INSTEAD}`}</span>
          </div>
        </div>

        {onRetry && (
          <div className="auth-alert-wrapper">
            <button type="button" className="auth-text-link" onClick={onRetry} disabled={isLoading}>
              Try the link again
            </button>
          </div>
        )}

        {message && (
          <div className="auth-alert-wrapper">
            <div className="auth-alert error" role="alert">
              <Icon name="exclamation-circle" className="auth-alert-icon" />
              <span>{message}</span>
            </div>
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="login-link-fallback-email">
              Email address
            </label>
            <input
              ref={emailInputRef}
              id="login-link-fallback-email"
              type="email"
              className="auth-form-input"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setValidationError(null);
                clearError();
              }}
              placeholder="you@email.com"
              required
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              // Focus lands here on arrival, and a live region inserted together
              // with its text is not reliably announced, so the notice is read
              // as part of the field's description too.
              aria-describedby="login-link-fallback-notice login-link-fallback-email-hint"
              aria-invalid={Boolean(validationError)}
            />
            <span id="login-link-fallback-email-hint" className="auth-help-text">
              We&apos;ll email you a 6-digit sign-in code.
            </span>
          </div>

          <PrivacyLegalNotice />

          <button type="submit" className="auth-form-submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <span className="auth-spinner" />
                Sending code...
              </>
            ) : (
              'Send sign-in code'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
