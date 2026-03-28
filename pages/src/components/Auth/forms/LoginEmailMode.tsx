import type { FormEvent, RefObject } from 'react';

interface LoginEmailModeProps {
  email: string;
  isLoading: boolean;
  emailInputRef: RefObject<HTMLInputElement | null>;
  onEmailChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSwitchToPassword: () => void;
}

export const LoginEmailMode = ({
  email,
  isLoading,
  emailInputRef,
  onEmailChange,
  onSubmit,
  onSwitchToPassword,
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

      <div style={{ textAlign: 'center' }}>
        <button type="button" className="auth-text-link" onClick={onSwitchToPassword} style={{ fontSize: '0.8125rem' }}>
          Sign in with password instead
        </button>
      </div>
    </form>
  );
};
