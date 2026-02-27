import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { resendVerification } from '../../../services/auth';
import '../Auth.css';

export const VerifyPending = () => {
  const { pendingEmail, setPendingEmail } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [isResending, setIsResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);
  const emailFromQuery = searchParams.get('email');

  const resolvedEmail = useMemo(
    () => pendingEmail || emailFromQuery || null,
    [pendingEmail, emailFromQuery],
  );

  useEffect(() => {
    if (!pendingEmail && emailFromQuery) {
      setPendingEmail(emailFromQuery);
    }
  }, [pendingEmail, emailFromQuery, setPendingEmail]);

  const handleResend = async () => {
    if (!resolvedEmail) return;

    setIsResending(true);
    setResendMessage(null);
    setResendError(null);

    try {
      await resendVerification(resolvedEmail);
      setResendMessage('Verification email sent! Please check your inbox.');
    } catch {
      setResendError('Failed to resend. Please try again later.');
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-page-card">
        <div className="auth-verify-pending">
          <div className="auth-verify-icon">
            <i className="fa fa-envelope-o" />
          </div>

          <h3 className="auth-verify-title">Check your email</h3>

          <p className="auth-verify-text">
            We've sent a verification link to{' '}
            <span className="auth-verify-email">{resolvedEmail || 'your email'}</span>.
            <br />
            Click the link in the email to activate your account.
          </p>

          {resendMessage && (
            <div className="auth-alert success" style={{ marginBottom: '1rem' }}>
              <i className="fa fa-check-circle auth-alert-icon" />
              <span>{resendMessage}</span>
            </div>
          )}

          {resendError && (
            <div className="auth-alert error" style={{ marginBottom: '1rem' }}>
              <i className="fa fa-exclamation-circle auth-alert-icon" />
              <span>{resendError}</span>
            </div>
          )}

          <div className="auth-verify-actions">
            <button
              type="button"
              className="auth-verify-resend"
              onClick={handleResend}
              disabled={isResending}
            >
              {isResending ? 'Sending...' : "Didn't receive it? Resend"}
            </button>

            <button
              type="button"
              className="auth-switch-link"
              onClick={() => navigate('/login')}
              style={{ marginTop: '0.5rem' }}
            >
              Back to login
            </button>

            <button
              type="button"
              className="auth-switch-link"
              onClick={() => navigate('/')}
              style={{ marginTop: '0.25rem', color: '#6b7280' }}
            >
              Back to home
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
