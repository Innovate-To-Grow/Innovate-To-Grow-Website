import type {FormEvent} from 'react';
import {CodeInput} from '../../forms/CodeInput';
import {StatusAlert} from '../../shared/StatusAlert';

interface PasswordSectionProps {
  passwordCodeRequested: boolean;
  passwordCode: string;
  passwordVerificationToken: string | null;
  newPassword: string;
  confirmPassword: string;
  passwordLoading: boolean;
  passwordMessage: string | null;
  passwordError: string | null;
  onPasswordRequestCode: () => void;
  onPasswordVerifyCode: (event: FormEvent) => void;
  onPasswordConfirm: (event: FormEvent) => void;
  onPasswordCodeChange: (value: string) => void;
  onNewPasswordChange: (value: string) => void;
  onConfirmPasswordChange: (value: string) => void;
}

export const PasswordSection = ({
  passwordCodeRequested,
  passwordCode,
  passwordVerificationToken,
  newPassword,
  confirmPassword,
  passwordLoading,
  passwordMessage,
  passwordError,
  onPasswordRequestCode,
  onPasswordVerifyCode,
  onPasswordConfirm,
  onPasswordCodeChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
}: PasswordSectionProps) => (
  <div className="account-section account-section--full-width">
    <div className="account-password-section">
      <div className="account-password-header">
        <div>
          <h2 className="account-section-title">Change Password</h2>
          <p className="account-password-help">Use a verification code sent to your email before setting a new password.</p>
        </div>
        {!passwordCodeRequested && !passwordVerificationToken ? (
          <button
            type="button"
            className="auth-form-submit account-action-primary account-action-primary--inline"
            onClick={onPasswordRequestCode}
            disabled={passwordLoading}
          >
            {passwordLoading ? <><span className="auth-spinner" /> Sending...</> : 'Send Code'}
          </button>
        ) : null}
      </div>

      {passwordMessage ? <StatusAlert tone="success" message={passwordMessage} /> : null}
      {passwordError ? <StatusAlert tone="error" message={passwordError} /> : null}

      {passwordCodeRequested && !passwordVerificationToken ? (
        <form className="account-password-form" onSubmit={onPasswordVerifyCode}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-password-code">Verification Code</label>
            <CodeInput value={passwordCode} onChange={onPasswordCodeChange} disabled={passwordLoading} />
          </div>
          <div className="account-action-row">
            <button
              type="submit"
              className="auth-form-submit account-action-primary"
              disabled={passwordLoading || passwordCode.length !== 6}
            >
              {passwordLoading ? <><span className="auth-spinner" /> Verifying...</> : 'Verify Code'}
            </button>
          </div>
        </form>
      ) : null}

      {passwordVerificationToken ? (
        <form className="account-password-form" onSubmit={onPasswordConfirm}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-new-password">New Password</label>
            <input
              id="account-new-password"
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
            <label className="auth-form-label" htmlFor="account-confirm-password">Confirm Password</label>
            <input
              id="account-confirm-password"
              type="password"
              className="auth-form-input"
              value={confirmPassword}
              onChange={(event) => onConfirmPasswordChange(event.target.value)}
              autoComplete="new-password"
              placeholder="Re-enter your password"
              required
            />
          </div>
          <div className="account-action-row">
            <button
              type="submit"
              className="auth-form-submit account-action-primary"
              disabled={passwordLoading || !newPassword || !confirmPassword}
            >
              {passwordLoading ? <><span className="auth-spinner" /> Saving...</> : 'Change Password'}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  </div>
);
