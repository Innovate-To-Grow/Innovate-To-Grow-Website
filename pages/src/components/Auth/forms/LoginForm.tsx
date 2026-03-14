import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export const LoginForm = () => {
  const {
    login,
    requestEmailAuthCode,
    requiresProfileCompletion,
    error,
    isLoading,
    clearError,
  } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    try {
      const response = await requestEmailAuthCode(email);
      setInfoMessage(response.message);
      navigate(`/verify-email?flow=auth&email=${encodeURIComponent(email.trim().toLowerCase())}`);
    } catch {
      // Error handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    try {
      await login(email, password);
      navigate(requiresProfileCompletion ? '/complete-profile' : '/account', { replace: true });
    } catch {
      // Error handled by context
    }
  };

  const switchMode = (toPassword: boolean) => {
    setShowPasswordForm(toPassword);
    setPassword('');
    clearError();
    setInfoMessage(null);
  };

  return (
    <>
      {infoMessage && (
        <div className="auth-alert-wrapper">
          <div className="auth-alert info" role="status">
            <i className="fa fa-info-circle auth-alert-icon" aria-hidden />
            <span>{infoMessage}</span>
          </div>
        </div>
      )}

      {error && (
        <div className="auth-alert-wrapper">
          <div className="auth-alert error" role="alert">
            <i className="fa fa-exclamation-circle auth-alert-icon" aria-hidden />
            <span>{error}</span>
          </div>
        </div>
      )}

      {showPasswordForm ? (
        <form className="auth-form" onSubmit={handlePasswordSubmit}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="login-email">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              className="auth-form-input"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                clearError();
                setInfoMessage(null);
              }}
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
              onChange={(event) => {
                setPassword(event.target.value);
                clearError();
              }}
              placeholder="Enter your password"
              required
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            className="auth-form-submit"
            disabled={isLoading || !email || !password}
          >
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
            <button
              type="button"
              className="auth-text-link"
              onClick={() => switchMode(false)}
              style={{ fontSize: '0.8125rem' }}
            >
              Sign in with email code
            </button>
            <Link to="/forgot-password" className="auth-text-link" style={{ fontSize: '0.8125rem' }}>
              Forgot password?
            </Link>
          </div>
        </form>
      ) : (
        <form className="auth-form" onSubmit={handleEmailSubmit}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="login-email">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              className="auth-form-input"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                clearError();
                setInfoMessage(null);
              }}
              placeholder="your@email.com"
              required
              autoComplete="email"
            />
            <span className="auth-help-text">
              We&apos;ll sign you in if this email already exists, or start your account setup if it&apos;s new.
            </span>
          </div>

          <button
            type="submit"
            className="auth-form-submit"
            disabled={isLoading || !email}
          >
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
            <button
              type="button"
              className="auth-text-link"
              onClick={() => switchMode(true)}
              style={{ fontSize: '0.8125rem' }}
            >
              Sign in with password instead
            </button>
          </div>
        </form>
      )}
    </>
  );
};
