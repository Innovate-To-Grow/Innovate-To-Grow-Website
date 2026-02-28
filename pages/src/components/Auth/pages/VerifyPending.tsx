import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { resendVerification } from '../../../services/auth';
import { CodeInput } from '../forms/CodeInput';
import '../Auth.css';

export const VerifyPending = () => {
  const { pendingEmail, setPendingEmail, verifyEmailCode, error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [code, setCode] = useState('');
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

  const handleVerify = async (e: FormEvent) => {
    e.preventDefault();
    if (!resolvedEmail || code.length !== 6) return;

    setResendMessage(null);
    setResendError(null);

    try {
      await verifyEmailCode(resolvedEmail, code);
      navigate('/account', { replace: true });
    } catch {
      // Error is handled by context
    }
  };

  const handleResend = async () => {
    if (!resolvedEmail) return;

    setIsResending(true);
    setResendMessage(null);
    setResendError(null);
    clearError();

    try {
      await resendVerification(resolvedEmail);
      setCode('');
      setResendMessage('New verification code sent! Please check your inbox.');
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

          <h3 className="auth-verify-title">Verify your email</h3>

          <p className="auth-verify-text">
            We've sent a 6-digit verification code to{' '}
            <span className="auth-verify-email">{resolvedEmail || 'your email'}</span>.
            <br />
            Enter the code below to activate your account.
          </p>

          {error && (
            <div className="auth-alert error" style={{ marginBottom: '1rem' }}>
              <i className="fa fa-exclamation-circle auth-alert-icon" />
              <span>{error}</span>
            </div>
          )}

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

          <form onSubmit={handleVerify}>
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
              style={{ width: '100%', marginTop: '0.5rem' }}
            >
              {isLoading ? (
                <>
                  <span className="auth-spinner" />
                  Verifying...
                </>
              ) : (
                'Verify Email'
              )}
            </button>
          </form>

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
