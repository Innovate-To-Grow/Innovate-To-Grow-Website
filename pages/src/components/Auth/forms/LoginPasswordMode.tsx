import { Link } from 'react-router-dom';
import type { FormEvent, RefObject } from 'react';

interface LoginPasswordModeProps {
  email: string;
  password: string;
  isLoading: boolean;
  emailInputRef: RefObject<HTMLInputElement | null>;
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
  onEmailChange,
  onPasswordChange,
  onSubmit,
  onSwitchToCode,
}: LoginPasswordModeProps) => {
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
          Sign in with email code
        </button>
        <Link to="/forgot-password" className="auth-text-link" style={{ fontSize: '0.8125rem' }}>
          Forgot password?
        </Link>
      </div>
    </form>
  );
};
