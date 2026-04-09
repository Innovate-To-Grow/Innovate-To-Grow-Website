import type {FormEvent} from 'react';
import type {ContactPhone} from '../../../services/auth';
import {CodeInput} from '../forms/CodeInput';
import {StatusAlert} from '../shared/StatusAlert';
import {formatPhoneDisplay} from './internal/helpers';

interface PhonePendingVerifyPanelProps {
  phone: ContactPhone;
  verifyCode: string;
  verifyLoading: boolean;
  verifyError: string | null;
  resendLoading: boolean;
  abandonLoading: boolean;
  onVerifyCodeChange: (value: string) => void;
  onVerifySubmit: (event: FormEvent) => void;
  onResend: () => void;
  onAbandon: () => void;
}

export const PhonePendingVerifyPanel = ({
  phone,
  verifyCode,
  verifyLoading,
  verifyError,
  resendLoading,
  abandonLoading,
  onVerifyCodeChange,
  onVerifySubmit,
  onResend,
  onAbandon,
}: PhonePendingVerifyPanelProps) => (
  <div className="email-center-add-form email-center-pending-verify">
    <h3 className="account-subsection-title email-center-pending-verify-title">Verify phone number</h3>
    <p className="account-status-text email-center-pending-verify-intro">
      Enter the 6-digit code we sent to{' '}
      <strong>{formatPhoneDisplay(phone.phone_number, phone.region)}</strong>. Verification is required to save this number.
    </p>
    <form onSubmit={onVerifySubmit} className="email-center-pending-verify-form">
      <div className="email-center-pending-verify-code">
        <CodeInput value={verifyCode} onChange={onVerifyCodeChange} disabled={verifyLoading} />
      </div>
      <div className="email-center-pending-verify-actions">
        <button
          type="submit"
          className="auth-form-submit account-action-primary email-center-pending-verify-submit"
          disabled={verifyLoading || verifyCode.length !== 6}
        >
          {verifyLoading ? <><span className="auth-spinner" /> Submitting...</> : 'Submit code'}
        </button>
        <div className="email-center-pending-verify-actions-row">
          <button
            type="button"
            className="email-center-btn verify email-center-pending-verify-secondary-btn"
            disabled={resendLoading || abandonLoading}
            onClick={onResend}
          >
            {resendLoading ? 'Sending...' : 'Resend Code'}
          </button>
          <button
            type="button"
            className="email-center-btn delete email-center-pending-verify-secondary-btn"
            disabled={abandonLoading || verifyLoading}
            onClick={onAbandon}
          >
            {abandonLoading ? 'Removing...' : 'Discard number'}
          </button>
        </div>
      </div>
    </form>
    {verifyError ? (
      <div className="email-center-pending-verify-alert">
        <StatusAlert tone="error" message={verifyError} />
      </div>
    ) : null}
  </div>
);
