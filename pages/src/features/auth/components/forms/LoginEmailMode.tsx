import type { FormEvent, RefObject } from 'react';
import { PrivacyLegalNotice } from '../shared/PrivacyLegalNotice';

interface LoginEmailModeProps {
  email: string;
  isLoading: boolean;
  emailInputRef: RefObject<HTMLInputElement | null>;
  onEmailChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSwitchToPassword: () => void;
  onSwitchToPhone: () => void;
}

export const LoginEmailMode = ({
  email,
  isLoading,
  emailInputRef,
  onEmailChange,
  onSubmit,
  onSwitchToPassword,
  onSwitchToPhone,
}: LoginEmailModeProps) => {
  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="login-email">
          Email
        </label>
        <input
          ref={emailInputRef}
          id="login-email"
          type="email"
          className="auth-form-input"
          value={email}
          onChange={(event) => onEmailChange(event.target.value)}
          placeholder="your@email.com"
          required
          autoComplete="email"
        />
        <span className="auth-help-text">
          We&apos;ll sign you in if this email already exists, or start your account setup if it&apos;s new.
        </span>
      </div>

      <PrivacyLegalNotice />

      <button type="submit" className="auth-form-submit" disabled={isLoading || !email}>
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Sending code...
          </>
        ) : (
          'Continue with Email'
        )}
      </button>

      <div className="auth-inline-links" style={{ justifyContent: 'center' }}>
        <button type="button" className="auth-text-link" onClick={onSwitchToPhone} style={{ fontSize: '0.8125rem' }}>
          Use phone number instead
        </button>
        <button type="button" className="auth-text-link" onClick={onSwitchToPassword} style={{ fontSize: '0.8125rem' }}>
          Sign in with password instead
        </button>
      </div>
    </form>
  );
};
