import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export const LoginForm = () => {
  const {
    requestEmailAuthCode,
    error,
    isLoading,
    clearError,
  } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
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

      <form className="auth-form" onSubmit={handleSubmit}>
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
      </form>
    </>
  );
};
