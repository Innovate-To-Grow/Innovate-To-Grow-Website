import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { CodeInput } from './CodeInput';

type LoginMode = 'password' | 'code';

export const LoginForm = () => {
  const { login, requestLoginCode, verifyLoginCode, error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();

  const [loginMode, setLoginMode] = useState<LoginMode>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [codeSentMessage, setCodeSentMessage] = useState<string | null>(null);

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await login(email, password);
      navigate('/account', { replace: true });
    } catch {
      // Error is handled by context
    }
  };

  const handleSendCode = async (e: FormEvent) => {
    e.preventDefault();
    setCodeSentMessage(null);
    try {
      await requestLoginCode(email);
      setCodeSent(true);
      setCodeSentMessage('Verification code sent to your email.');
    } catch {
      // Error is handled by context
    }
  };

  const handleVerifyCode = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await verifyLoginCode(email, code);
      navigate('/account', { replace: true });
    } catch {
      // Error is handled by context
    }
  };

  const handleResendCode = async () => {
    setCodeSentMessage(null);
    clearError();
    try {
      await requestLoginCode(email);
      setCode('');
      setCodeSentMessage('New code sent to your email.');
    } catch {
      // Error is handled by context
    }
  };

  const switchMode = (mode: LoginMode) => {
    setLoginMode(mode);
    setCode('');
    setCodeSent(false);
    setCodeSentMessage(null);
    clearError();
  };

  return (
    <>
      {error && (
        <div className="auth-alert error" style={{ margin: '0 1.5rem' }}>
          <i className="fa fa-exclamation-circle auth-alert-icon" />
          <span>{error}</span>
        </div>
      )}

      {codeSentMessage && !error && (
        <div className="auth-alert success" style={{ margin: '0 1.5rem' }}>
          <i className="fa fa-check-circle auth-alert-icon" />
          <span>{codeSentMessage}</span>
        </div>
      )}

      {loginMode === 'password' ? (
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
              onChange={(e) => {
                setEmail(e.target.value);
                clearError();
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
              onChange={(e) => {
                setPassword(e.target.value);
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

          <div className="auth-mode-toggle">
            <button
              type="button"
              className="auth-mode-toggle-link"
              onClick={() => switchMode('code')}
            >
              Sign in with email code instead
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
      ) : !codeSent ? (
        <form className="auth-form" onSubmit={handleSendCode}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="login-email-code">
              Email
            </label>
            <input
              id="login-email-code"
              type="email"
              className="auth-form-input"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                clearError();
              }}
              placeholder="your@email.com"
              required
              autoComplete="email"
            />
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
              'Send Code'
            )}
          </button>

          <div className="auth-mode-toggle">
            <button
              type="button"
              className="auth-mode-toggle-link"
              onClick={() => switchMode('password')}
            >
              Sign in with password instead
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
      ) : (
        <form className="auth-form" onSubmit={handleVerifyCode}>
          <p className="auth-code-info">
            Enter the 6-digit code sent to <span className="auth-code-email">{email}</span>
          </p>

          <CodeInput
            value={code}
            onChange={(val) => {
              setCode(val);
              clearError();
            }}
            disabled={isLoading}
          />

          <button
            type="submit"
            className="auth-form-submit"
            disabled={isLoading || code.length !== 6}
          >
            {isLoading ? (
              <>
                <span className="auth-spinner" />
                Verifying...
              </>
            ) : (
              'Verify & Sign In'
            )}
          </button>

          <div className="auth-mode-toggle">
            <button
              type="button"
              className="auth-resend-btn"
              onClick={handleResendCode}
              disabled={isLoading}
            >
              Resend code
            </button>
          </div>

          <div className="auth-mode-toggle">
            <button
              type="button"
              className="auth-mode-toggle-link"
              onClick={() => switchMode('password')}
            >
              Sign in with password instead
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
      )}
    </>
  );
};
