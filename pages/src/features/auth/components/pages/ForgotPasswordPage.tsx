import '../auth.css';
import {Icon} from '@/components/Icon/Icon';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router';
import { useAuth } from '../AuthContext';

export const ForgotPasswordPage = () => {
  const { isAuthenticated, requiresProfileCompletion, requestPasswordReset, error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  if (isAuthenticated) {
    return <Navigate to={requiresProfileCompletion ? '/complete-profile' : '/account'} replace />;
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
      <header className="auth-page-header">
        <h1 className="itg-page-title auth-page-title">Forgot Password</h1>
        <p className="itg-page-meta auth-page-subtitle">Request a verification code to reset your password</p>
      </header>
      <div className="itg-panel auth-page-card">

        {infoMessage && (
          <div className="auth-alert-wrapper">
            <div className="auth-alert info" role="status">
              <Icon name="info-circle" className="auth-alert-icon" />
              <span>{infoMessage}</span>
            </div>
          </div>
        )}

        {error && (
          <div className="auth-alert-wrapper">
            <div className="auth-alert error" role="alert">
              <Icon name="exclamation-circle" className="auth-alert-icon" />
              <span>{error}</span>
            </div>
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-form-group">
            <label className="itg-label auth-form-label" htmlFor="forgot-email">
              Email or Phone
            </label>
            <input
              id="forgot-email"
              type="text"
              className="itg-input auth-form-input"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                clearError();
                setInfoMessage(null);
              }}
              placeholder="you@email.com or (201) 555-0123"
              autoComplete="username"
              required
            />
            <span className="auth-help-text">
              Use your account email or a verified phone number linked to the account.
            </span>
          </div>

          <button type="submit" className="itg-btn itg-btn-primary auth-form-submit" disabled={isLoading || !email}>
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
            <button type="button" className="itg-btn itg-btn-text auth-text-link" onClick={() => navigate('/login')}>
              Back to login
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
