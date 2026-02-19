import { useState } from 'react';
import { useAuth } from './AuthContext';
import { resendVerification } from '../../services/auth';

export const VerifyPending = () => {
  const { pendingEmail, openModal, closeModal } = useAuth();
  const [isResending, setIsResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);

  const handleResend = async () => {
    if (!pendingEmail) return;

    setIsResending(true);
    setResendMessage(null);
    setResendError(null);

    try {
      await resendVerification(pendingEmail);
      setResendMessage('Verification email sent! Please check your inbox.');
    } catch {
      setResendError('Failed to resend. Please try again later.');
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="auth-verify-pending">
      <div className="auth-verify-icon">
        <i className="fa fa-envelope-o" />
      </div>

      <h3 className="auth-verify-title">Check your email</h3>

      <p className="auth-verify-text">
        We've sent a verification link to{' '}
        <span className="auth-verify-email">{pendingEmail || 'your email'}</span>.
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
          onClick={() => openModal('login')}
          style={{ marginTop: '0.5rem' }}
        >
          Back to login
        </button>

        <button
          type="button"
          className="auth-switch-link"
          onClick={closeModal}
          style={{ marginTop: '0.25rem', color: '#6b7280' }}
        >
          Close
        </button>
      </div>
    </div>
  );
};

