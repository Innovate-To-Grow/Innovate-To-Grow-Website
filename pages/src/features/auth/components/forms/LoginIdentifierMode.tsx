import type { FormEvent, RefObject } from 'react';
import { PrivacyLegalNotice } from '../shared/PrivacyLegalNotice';
import { identifyLoginInput } from '../sections/internal/identifyLoginInput';

interface LoginIdentifierModeProps {
  /** Raw text the user typed (email address or phone number). */
  identifier: string;
  isLoading: boolean;
  identifierInputRef: RefObject<HTMLInputElement | null>;
  onIdentifierChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSwitchToPassword: () => void;
}

export const LoginIdentifierMode = ({
  identifier,
  isLoading,
  identifierInputRef,
  onIdentifierChange,
  onSubmit,
  onSwitchToPassword,
}: LoginIdentifierModeProps) => {
  const parsed = identifyLoginInput(identifier);
  const canSubmit = parsed.type !== 'invalid';
  // Only flag invalid once the user has actually typed something, so an empty
  // field isn't announced as an error on first focus.
  const showInvalid = parsed.type === 'invalid' && identifier.trim().length > 0;
  // Live feedback so the smart detection is visible as the user types.
  const hint =
    parsed.type === 'email'
      ? "We'll email you a 6-digit sign-in code."
      : parsed.type === 'phone'
        ? "We'll text you a 6-digit sign-in code (US numbers only)."
        : 'Use your email address or a US phone number. New here? This creates your account.';

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="login-identifier">
          Email or phone number
        </label>
        <input
          ref={identifierInputRef}
          id="login-identifier"
          type="text"
          className="auth-form-input"
          value={identifier}
          onChange={(event) => onIdentifierChange(event.target.value)}
          placeholder="you@email.com or (201)555-0123"
          required
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          aria-describedby="login-identifier-hint"
          aria-invalid={showInvalid}
        />
        <span id="login-identifier-hint" className="auth-help-text">
          {hint}
        </span>
      </div>

      <PrivacyLegalNotice />

      <button type="submit" className="auth-form-submit" disabled={isLoading || !canSubmit}>
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Sending code...
          </>
        ) : (
          'Continue'
        )}
      </button>

      <div className="auth-inline-links" style={{ justifyContent: 'center' }}>
        <button type="button" className="auth-text-link" onClick={onSwitchToPassword} style={{ fontSize: '0.8125rem' }}>
          Sign in with password instead
        </button>
      </div>
    </form>
  );
};
