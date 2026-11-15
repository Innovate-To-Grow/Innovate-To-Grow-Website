import {type RefObject} from 'react';
import {Icon} from '@/components/Icon/Icon';
import type {LoginLinkFailureKind} from '@/features/auth/api';

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

interface FallbackAlertsProps {
  kind: LoginLinkFallbackKind;
  onRetry?: () => void;
  isLoading: boolean;
  message: string | null;
}

/** The notice for the failed link, a retry when it can help, and any sign-in error. */
export const FallbackAlerts = ({kind, onRetry, isLoading, message}: FallbackAlertsProps) => (
  <>
    <div className="auth-alert-wrapper">
      <div className="auth-alert info" role="status">
        <Icon name="info-circle" className="auth-alert-icon" />
        <span id="login-link-fallback-notice">{`${NOTICES[kind]} ${INSTEAD}`}</span>
      </div>
    </div>

    {onRetry && (
      <div className="auth-alert-wrapper">
        <button type="button" className="itg-btn itg-btn-text auth-text-link" onClick={onRetry} disabled={isLoading}>
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
  </>
);

interface FallbackEmailFieldProps {
  inputRef: RefObject<HTMLInputElement | null>;
  email: string;
  invalid: boolean;
  onChange: (value: string) => void;
}

/** The email field, described by the notice so it is read on arrival. */
export const FallbackEmailField = ({inputRef, email, invalid, onChange}: FallbackEmailFieldProps) => (
  <div className="auth-form-group">
    <label className="itg-label auth-form-label" htmlFor="login-link-fallback-email">
      Email address
    </label>
    <input
      ref={inputRef}
      id="login-link-fallback-email"
      type="email"
      className="itg-input auth-form-input"
      value={email}
      onChange={(event) => onChange(event.target.value)}
      placeholder="you@email.com"
      required
      autoComplete="email"
      autoCapitalize="none"
      spellCheck={false}
      // Focus lands here on arrival, and a live region inserted together
      // with its text is not reliably announced, so the notice is read
      // as part of the field's description too.
      aria-describedby="login-link-fallback-notice login-link-fallback-email-hint"
      aria-invalid={invalid}
    />
    <span id="login-link-fallback-email-hint" className="auth-help-text">
      We&apos;ll email you a 6-digit sign-in code.
    </span>
  </div>
);
