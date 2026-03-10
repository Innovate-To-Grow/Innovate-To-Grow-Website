import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { CodeInput } from '../forms/CodeInput';
import { useAuth } from '../AuthContext';
import '../Auth.css';

type VerifyFlow = 'login' | 'register' | 'reset' | 'change';

const FLOW_META: Record<VerifyFlow, { title: string; subtitle: string; buttonLabel: string }> = {
  login: {
    title: 'Verify Login',
    subtitle: 'Enter the 6-digit code we sent to finish signing in.',
    buttonLabel: 'Verify and Sign In',
  },
  register: {
    title: 'Verify Your Email',
    subtitle: 'Enter the 6-digit code to activate your new account.',
    buttonLabel: 'Verify and Activate',
  },
  reset: {
    title: 'Reset Password',
    subtitle: 'Enter the 6-digit code to continue resetting your password.',
    buttonLabel: 'Verify Code',
  },
  change: {
    title: 'Confirm Password Change',
    subtitle: 'Enter the 6-digit code we sent before setting a new password.',
    buttonLabel: 'Verify Code',
  },
};

const isVerifyFlow = (value: string | null): value is VerifyFlow => {
  return value === 'login' || value === 'register' || value === 'reset' || value === 'change';
};

export const VerifyEmailPage = () => {
  const { isAuthenticated } = useAuth();
  const [searchParams] = useSearchParams();

  const flowParam = searchParams.get('flow');
  const email = searchParams.get('email')?.trim().toLowerCase() ?? '';

  if (!isVerifyFlow(flowParam) || !email) {
    return <Navigate to="/login" replace />;
  }

  if (flowParam === 'change' && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if ((flowParam === 'login' || flowParam === 'register') && isAuthenticated) {
    return <Navigate to="/account" replace />;
  }

  return <VerifyEmailPageContent key={`${flowParam}:${email}`} flow={flowParam} email={email} />;
};

interface VerifyEmailPageContentProps {
  flow: VerifyFlow;
  email: string;
}

const VerifyEmailPageContent = ({ flow, email }: VerifyEmailPageContentProps) => {
  const {
    error,
    isLoading,
    clearError,
    verifyLoginCode,
    verifyRegistrationCode,
    resendRegistrationCode,
    requestLoginCode,
    requestPasswordReset,
    verifyPasswordResetCode,
    confirmPasswordReset,
    requestPasswordChangeCode,
    verifyPasswordChangeCode,
    confirmPasswordChange,
  } = useAuth();
  const navigate = useNavigate();

  const [code, setCode] = useState('');
  const [verificationToken, setVerificationToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localMessage, setLocalMessage] = useState<string | null>(null);
  const [localSuccess, setLocalSuccess] = useState<string | null>(null);

  useEffect(() => {
    clearError();
  }, [clearError]);

  const meta = FLOW_META[flow];

  const handleVerify = async (event: FormEvent) => {
    event.preventDefault();
    setLocalMessage(null);
    setLocalSuccess(null);
    try {
      if (flow === 'login') {
        await verifyLoginCode(email, code);
        navigate('/account', { replace: true });
        return;
      }
      if (flow === 'register') {
        await verifyRegistrationCode(email, code);
        navigate('/account', { replace: true });
        return;
      }
      if (flow === 'reset') {
        const response = await verifyPasswordResetCode(email, code);
        setVerificationToken(response.verification_token);
        setLocalMessage('Code verified. Set your new password below.');
        return;
      }
      const response = await verifyPasswordChangeCode(email, code);
      setVerificationToken(response.verification_token);
      setLocalMessage('Code verified. Set your new password below.');
    } catch {
      // handled by context
    }
  };

  const handleResend = async () => {
    setLocalMessage(null);
    setLocalSuccess(null);
    try {
      if (flow === 'login') {
        const response = await requestLoginCode(email);
        setLocalMessage(response.message);
        return;
      }
      if (flow === 'register') {
        const response = await resendRegistrationCode(email);
        setLocalMessage(response.message);
        return;
      }
      if (flow === 'reset') {
        const response = await requestPasswordReset(email);
        setLocalMessage(response.message);
        return;
      }
      const response = await requestPasswordChangeCode(email);
      setLocalMessage(response.message);
    } catch {
      // handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!verificationToken) return;
    setLocalMessage(null);
    setLocalSuccess(null);
    try {
      if (flow === 'reset') {
        const response = await confirmPasswordReset(verificationToken, newPassword, confirmPassword);
        setLocalSuccess(response.message);
        window.setTimeout(() => navigate('/login', { replace: true }), 900);
        return;
      }
      const response = await confirmPasswordChange(verificationToken, newPassword, confirmPassword);
      setLocalSuccess(response.message);
      window.setTimeout(() => navigate('/account', { replace: true }), 900);
    } catch {
      // handled by context
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-page-card">
        <div className="auth-page-header">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
          <h1 className="auth-page-title">{meta.title}</h1>
          <p className="auth-page-subtitle">{meta.subtitle}</p>
        </div>

        <div className="auth-verification-intro">
          <span className="auth-verification-label">Sending to</span>
          <strong>{email}</strong>
        </div>

        {localMessage && (
          <div className="auth-alert info" style={{ margin: '0 1.5rem' }}>
            <i className="fa fa-info-circle auth-alert-icon" />
            <span>{localMessage}</span>
          </div>
        )}

        {localSuccess && (
          <div className="auth-alert success" style={{ margin: '0 1.5rem' }}>
            <i className="fa fa-check-circle auth-alert-icon" />
            <span>{localSuccess}</span>
          </div>
        )}

        {error && (
          <div className="auth-alert error" style={{ margin: '0 1.5rem' }}>
            <i className="fa fa-exclamation-circle auth-alert-icon" />
            <span>{error}</span>
          </div>
        )}

        {verificationToken ? (
          <form className="auth-form" onSubmit={handlePasswordSubmit}>
            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="verify-new-password">
                New Password
              </label>
              <input
                id="verify-new-password"
                type="password"
                className="auth-form-input"
                value={newPassword}
                onChange={(event) => {
                  setNewPassword(event.target.value);
                  clearError();
                }}
                autoComplete="new-password"
                placeholder="At least 8 characters"
                minLength={8}
                required
              />
            </div>

            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="verify-confirm-password">
                Confirm Password
              </label>
              <input
                id="verify-confirm-password"
                type="password"
                className="auth-form-input"
                value={confirmPassword}
                onChange={(event) => {
                  setConfirmPassword(event.target.value);
                  clearError();
                }}
                autoComplete="new-password"
                placeholder="Re-enter your password"
                required
              />
            </div>

            <button
              type="submit"
              className="auth-form-submit"
              disabled={isLoading || !newPassword || !confirmPassword}
            >
              {isLoading ? (
                <>
                  <span className="auth-spinner" />
                  Saving password...
                </>
              ) : (
                flow === 'reset' ? 'Reset Password' : 'Change Password'
              )}
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleVerify}>
            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="verify-email-code">
                Verification Code
              </label>
              <CodeInput
                value={code}
                onChange={(value) => {
                  setCode(value);
                  clearError();
                }}
                disabled={isLoading}
              />
            </div>

            <button type="submit" className="auth-form-submit" disabled={isLoading || code.length !== 6}>
              {isLoading ? (
                <>
                  <span className="auth-spinner" />
                  Verifying...
                </>
              ) : (
                meta.buttonLabel
              )}
            </button>

            <div className="auth-inline-links">
              <button type="button" className="auth-text-link" onClick={handleResend}>
                Resend code
              </button>
              <button
                type="button"
                className="auth-text-link"
                onClick={() => navigate(flow === 'change' ? '/account' : flow === 'reset' ? '/forgot-password' : '/login')}
              >
                {flow === 'change' ? 'Back to account' : 'Back'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
