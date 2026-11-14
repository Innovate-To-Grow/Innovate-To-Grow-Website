import {CodeInput} from '../../forms/CodeInput';
import {describeCodeField, HINT_ID, type VerifyEmailViewProps} from './verifyEmailViewProps';

type NewPasswordFormProps = Pick<
  VerifyEmailViewProps,
  'flow' | 'newPassword' | 'confirmPassword' | 'isLoading' | 'onNewPasswordChange' | 'onConfirmPasswordChange' | 'onPasswordSubmit'
>;

/** After a reset / change code is accepted: the new password, twice. */
export const NewPasswordForm = ({
  flow,
  newPassword,
  confirmPassword,
  isLoading,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onPasswordSubmit,
}: NewPasswordFormProps) => (
  <form className="auth-form" onSubmit={onPasswordSubmit}>
    <div className="auth-form-group">
      <label className="itg-label auth-form-label" htmlFor="verify-new-password">
        New Password
      </label>
      <input
        id="verify-new-password"
        type="password"
        className="itg-input auth-form-input"
        value={newPassword}
        onChange={(event) => onNewPasswordChange(event.target.value)}
        autoComplete="new-password"
        placeholder="At least 8 characters"
        minLength={8}
        required
      />
    </div>

    <div className="auth-form-group">
      <label className="itg-label auth-form-label" htmlFor="verify-confirm-password">
        Confirm Password
      </label>
      <input
        id="verify-confirm-password"
        type="password"
        className="itg-input auth-form-input"
        value={confirmPassword}
        onChange={(event) => onConfirmPasswordChange(event.target.value)}
        autoComplete="new-password"
        placeholder="Re-enter your password"
        required
      />
    </div>

    <button type="submit" className="itg-btn itg-btn-primary auth-form-submit" disabled={isLoading || !newPassword || !confirmPassword}>
      {isLoading ? <><span className="auth-spinner" /> Saving password...</> : flow === 'reset' ? 'Reset Password' : 'Change Password'}
    </button>
  </form>
);

type VerifyCodeFormProps = Pick<
  VerifyEmailViewProps,
  'flow' | 'code' | 'isLoading' | 'autoFocus' | 'hint' | 'localMessage' | 'buttonLabel' | 'onCodeChange' | 'onVerifySubmit' | 'onResend' | 'onBack'
>;

export const VerifyCodeForm = ({
  flow,
  code,
  isLoading,
  autoFocus = false,
  hint = null,
  localMessage,
  buttonLabel,
  onCodeChange,
  onVerifySubmit,
  onResend,
  onBack,
}: VerifyCodeFormProps) => (
  <form className="auth-form" onSubmit={onVerifySubmit}>
    <div className="auth-form-group">
      <label className="itg-label auth-form-label" htmlFor="verify-email-code">
        Verification Code
      </label>
      <CodeInput
        value={code}
        onChange={onCodeChange}
        disabled={isLoading}
        autoFocus={autoFocus}
        describedBy={describeCodeField(localMessage, hint)}
      />
      {hint ? (
        <span id={HINT_ID} className="auth-help-text">
          {hint}
        </span>
      ) : null}
    </div>

    <button type="submit" className="itg-btn itg-btn-primary auth-form-submit" disabled={isLoading || code.length !== 6}>
      {isLoading ? <><span className="auth-spinner" /> Verifying...</> : buttonLabel}
    </button>

    <div className="auth-inline-links">
      <button type="button" className="itg-btn itg-btn-text auth-text-link" onClick={onResend}>
        Resend code
      </button>
      <button type="button" className="itg-btn itg-btn-text auth-text-link" onClick={onBack}>
        {flow === 'change' ? 'Back to account' : 'Back'}
      </button>
    </div>
  </form>
);
