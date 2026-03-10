import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import '../Auth.css';

export const ForgotPasswordPage = () => {
  const { isAuthenticated, requestPasswordReset, error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  if (isAuthenticated) {
    return <Navigate to="/account" replace />;
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    try {
      const response = await requestPasswordReset(email);
      setInfoMessage(response.message);
      navigate(`/verify-email?flow=reset&email=${encodeURIComponent(email.trim().toLowerCase())}`, { replace: true });
    } catch {
      // handled by context
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-page-card">
        <div className="auth-page-header">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
          <h1 className="auth-page-title">Forgot Password</h1>
          <p className="auth-page-subtitle">Request a verification code to reset your password</p>
        </div>

        {infoMessage && (
          <div className="auth-alert info" style={{ margin: '0 1.5rem' }}>
            <i className="fa fa-info-circle auth-alert-icon" />
            <span>{infoMessage}</span>
          </div>
        )}

        {error && (
          <div className="auth-alert error" style={{ margin: '0 1.5rem' }}>
            <i className="fa fa-exclamation-circle auth-alert-icon" />
            <span>{error}</span>
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="forgot-email">
              Email
            </label>
            <input
              id="forgot-email"
              type="email"
              className="auth-form-input"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                clearError();
                setInfoMessage(null);
              }}
              placeholder="your@email.com"
              autoComplete="email"
              required
            />
            <span className="auth-help-text">
              Use your account email or any verified contact email linked to the account.
            </span>
          </div>

          <button type="submit" className="auth-form-submit" disabled={isLoading || !email}>
            {isLoading ? (
              <>
                <span className="auth-spinner" />
                Sending code...
              </>
            ) : (
              'Send Reset Code'
            )}
          </button>

          <div className="auth-inline-links">
            <button type="button" className="auth-text-link" onClick={() => navigate('/login')}>
              Back to login
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
