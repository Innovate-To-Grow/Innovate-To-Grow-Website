import type {FormEvent} from 'react';
import {CodeInput} from '../../forms/CodeInput';
import type {VerifyFlow} from './shared';

interface VerifyEmailViewProps {
  flow: VerifyFlow;
  email: string;
  title: string;
  subtitle: string;
  buttonLabel: string;
  code: string;
  verificationToken: string | null;
  newPassword: string;
  confirmPassword: string;
  localMessage: string | null;
  localSuccess: string | null;
  error: string | null;
  isLoading: boolean;
  onCodeChange: (value: string) => void;
  onNewPasswordChange: (value: string) => void;
  onConfirmPasswordChange: (value: string) => void;
  onVerifySubmit: (event: FormEvent) => void;
  onPasswordSubmit: (event: FormEvent) => void;
  onResend: () => void;
  onBack: () => void;
}

export const VerifyEmailView = ({
  flow,
  email,
  title,
  subtitle,
  buttonLabel,
  code,
  verificationToken,
  newPassword,
  confirmPassword,
  localMessage,
  localSuccess,
  error,
  isLoading,
  onCodeChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onVerifySubmit,
  onPasswordSubmit,
  onResend,
  onBack,
}: VerifyEmailViewProps) => (
  <div className="auth-page">
    <div className="auth-page-card">
      <div className="auth-page-header">
        <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
        <h1 className="auth-page-title">{title}</h1>
        <p className="auth-page-subtitle">{subtitle}</p>
      </div>

      <div className="auth-verification-intro">
        <span className="auth-verification-label">Sending to</span>
        <strong>{email}</strong>
      </div>

      {localMessage ? (
        <div className="auth-alert-wrapper">
          <div className="auth-alert info" role="status">
            <i className="fa fa-info-circle auth-alert-icon" aria-hidden />
            <span>{localMessage}</span>
          </div>
        </div>
      ) : null}

      {localSuccess ? (
        <div className="auth-alert-wrapper">
          <div className="auth-alert success" role="status">
            <i className="fa fa-check-circle auth-alert-icon" aria-hidden />
            <span>{localSuccess}</span>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="auth-alert-wrapper">
          <div className="auth-alert error" role="alert">
            <i className="fa fa-exclamation-circle auth-alert-icon" aria-hidden />
            <span>{error}</span>
          </div>
        </div>
      ) : null}

      {verificationToken ? (
        <form className="auth-form" onSubmit={onPasswordSubmit}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="verify-new-password">
              New Password
            </label>
            <input
              id="verify-new-password"
              type="password"
              className="auth-form-input"
              value={newPassword}
              onChange={(event) => onNewPasswordChange(event.target.value)}
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
              onChange={(event) => onConfirmPasswordChange(event.target.value)}
              autoComplete="new-password"
              placeholder="Re-enter your password"
              required
            />
          </div>

          <button type="submit" className="auth-form-submit" disabled={isLoading || !newPassword || !confirmPassword}>
            {isLoading ? <><span className="auth-spinner" /> Saving password...</> : flow === 'reset' ? 'Reset Password' : 'Change Password'}
          </button>
        </form>
      ) : (
        <form className="auth-form" onSubmit={onVerifySubmit}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="verify-email-code">
              Verification Code
            </label>
            <CodeInput value={code} onChange={onCodeChange} disabled={isLoading} />
          </div>

          <button type="submit" className="auth-form-submit" disabled={isLoading || code.length !== 6}>
            {isLoading ? <><span className="auth-spinner" /> Verifying...</> : buttonLabel}
          </button>

          <div className="auth-inline-links">
            <button type="button" className="auth-text-link" onClick={onResend}>
              Resend code
            </button>
            <button type="button" className="auth-text-link" onClick={onBack}>
              {flow === 'change' ? 'Back to account' : 'Back'}
            </button>
          </div>
        </form>
      )}
    </div>
  </div>
);
