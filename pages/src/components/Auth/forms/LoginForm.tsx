import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

type LoginMode = 'code' | 'password';

export const LoginForm = () => {
  const {
    login,
    requestLoginCode,
    error,
    isLoading,
    clearError,
  } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<LoginMode>('code');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const handlePasswordLogin = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await login(email, password);
      navigate('/account', { replace: true });
    } catch {
      // Error handled by context
    }
  };

  const handleRequestCode = async (e: FormEvent) => {
    e.preventDefault();
    setInfoMessage(null);
    try {
      const response = await requestLoginCode(email);
      setInfoMessage(response.message);
      navigate(`/verify-email?flow=login&email=${encodeURIComponent(email.trim().toLowerCase())}`);
    } catch {
      // Error handled by context
    }
  };

  const switchMode = (nextMode: LoginMode) => {
    setMode(nextMode);
    setInfoMessage(null);
    clearError();
  };

  return (
    <>
      <div className="auth-mode-toggle" role="tablist" aria-label="Login method">
        <button
          type="button"
          className={`auth-mode-tab ${mode === 'code' ? 'is-active' : ''}`}
          onClick={() => switchMode('code')}
        >
          Email Code
        </button>
        <button
          type="button"
          className={`auth-mode-tab ${mode === 'password' ? 'is-active' : ''}`}
          onClick={() => switchMode('password')}
        >
          Password
        </button>
      </div>

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

      <form className="auth-form" onSubmit={mode === 'code' ? handleRequestCode : handlePasswordLogin}>
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="login-email">
            Email
          </label>
          <input
            id="login-email"
            type="email"
            className="auth-form-input"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              clearError();
              setInfoMessage(null);
            }}
            placeholder="your@email.com"
            required
            autoComplete="email"
          />
          {mode === 'code' && (
            <span className="auth-help-text">
              You can sign in with your account email or any verified contact email.
            </span>
          )}
        </div>

        {mode === 'password' && (
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              className="auth-form-input"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                clearError();
              }}
              placeholder="Enter your password"
              required
              autoComplete="current-password"
            />
          </div>
        )}

        <button
          type="submit"
          className="auth-form-submit"
          disabled={isLoading || !email || (mode === 'password' && !password)}
        >
          {isLoading ? (
            <>
              <span className="auth-spinner" />
              {mode === 'code' ? 'Sending code...' : 'Signing in...'}
            </>
          ) : (
            mode === 'code' ? 'Send Login Code' : 'Sign In'
          )}
        </button>

        <div className="auth-inline-links">
          <button
            type="button"
            className="auth-text-link"
            onClick={() => navigate('/forgot-password')}
          >
            Forgot password?
          </button>
        </div>

        <div className="auth-switch">
          <p>Don't have an account?</p>
          <button
            type="button"
            className="auth-switch-link"
            onClick={() => navigate('/register')}
          >
            Create Account
          </button>
        </div>
      </form>
    </>
  );
};
