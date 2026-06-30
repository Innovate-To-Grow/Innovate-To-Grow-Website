import { Link } from 'react-router-dom';
import type { FormEvent, RefObject } from 'react';
import { PrivacyLegalNotice } from '../shared/PrivacyLegalNotice';

interface LoginPasswordModeProps {
  email: string;
  password: string;
  isLoading: boolean;
  emailInputRef: RefObject<HTMLInputElement | null>;
  /** Whether the current identifier was detected as a phone number. */
  isPhone: boolean;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSwitchToCode: () => void;
}

export const LoginPasswordMode = ({
  email,
  password,
  isLoading,
  emailInputRef,
  isPhone,
  onEmailChange,
  onPasswordChange,
  onSubmit,
  onSwitchToCode,
}: LoginPasswordModeProps) => {
  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="login-email">
          Email or Phone
        </label>
        <input
          ref={emailInputRef}
          id="login-email"
          type="text"
          className="auth-form-input"
          value={email}
          onChange={(event) => onEmailChange(event.target.value)}
          placeholder="you@email.com or (201) 555-0123"
          required
          autoComplete="username"
          aria-describedby={isPhone ? "login-password-phone-hint" : undefined}
        />
        {isPhone && (
          <span id="login-password-phone-hint" className="auth-help-text">
            If you created your account with a phone number and haven't set a password yet,
            use the verification code option below, then set a password from your account page.
          </span>
        )}
      </div>

      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="login-password">
          Password
        </label>
        <input
          id="login-password"
          type="password"
          className="auth-form-input"
          value={password}
          onChange={(event) => onPasswordChange(event.target.value)}
          placeholder="Enter your password"
          required
          autoComplete="current-password"
        />
      </div>

      <PrivacyLegalNotice />

      <button type="submit" className="auth-form-submit" disabled={isLoading || !email || !password}>
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Signing in...
          </>
        ) : (
          'Sign In'
        )}
      </button>

      <div className="auth-inline-links">
        <button type="button" className="auth-text-link" onClick={onSwitchToCode} style={{ fontSize: '0.8125rem' }}>
          Sign in with a verification code
        </button>
        <Link to="/forgot-password" className="auth-text-link" style={{ fontSize: '0.8125rem' }}>
          Forgot password?
        </Link>
      </div>
    </form>
  );
};
