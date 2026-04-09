import type {FormEvent} from 'react';
import type {ContactPhone} from '../../../services/auth';
import {CodeInput} from '../forms/CodeInput';
import {StatusAlert} from '../shared/StatusAlert';
import {formatPhoneDisplay} from './internal/helpers';

interface PhoneCardProps {
  phone: ContactPhone;
  verifyingId: string | null;
  verifyCode: string;
  verifyLoading: boolean;
  verifyError: string | null;
  resendLoading: boolean;
  onToggleSubscribe: (phone: ContactPhone) => void;
  onToggleVerify: (phoneId: string) => void;
  onVerifyCodeChange: (value: string) => void;
  onVerifySubmit: (event: FormEvent) => void;
  onResend: (phoneId: string) => void;
  onCancelVerify: () => void;
  onDelete: (phoneId: string) => void;
}

export const PhoneCard = ({
  phone,
  verifyingId,
  verifyCode,
  verifyLoading,
  verifyError,
  resendLoading,
  onToggleSubscribe,
  onToggleVerify,
  onVerifyCodeChange,
  onVerifySubmit,
  onResend,
  onCancelVerify,
  onDelete,
}: PhoneCardProps) => (
  <div className="email-center-card">
    <div className="email-center-row">
      <div className="email-center-card-main">
        <div className="email-center-card-heading">
          <span className="email-center-card-title">{formatPhoneDisplay(phone.phone_number, phone.region)}</span>
          <span className="email-center-badge primary">{phone.region_display}</span>
          <span className={`email-center-badge ${phone.verified ? 'verified' : 'unverified'}`}>
            {phone.verified ? 'Verified' : 'Unverified'}
          </span>
        </div>
        <div className="email-center-actions">
          <label className="email-center-toggle" aria-label="Allow SMS Message">
            <input type="checkbox" checked={phone.subscribe} onChange={() => onToggleSubscribe(phone)} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Allow SMS Message</span>
          </label>
          {!phone.verified && verifyingId !== phone.id ? (
            <button type="button" className="email-center-btn verify" onClick={() => onToggleVerify(phone.id)}>
              Verify
            </button>
          ) : null}
          <button type="button" className="email-center-btn delete" onClick={() => onDelete(phone.id)}>
            Remove
          </button>
        </div>
      </div>
    </div>

    {verifyingId === phone.id && !phone.verified ? (
      <div className="email-center-verify-inline">
        <p className="email-center-verify-hint">
          Enter the 6-digit code we sent by SMS, then tap Submit code.
        </p>
        <form onSubmit={onVerifySubmit} className="email-center-verify-form">
          <div className="email-center-verify-code-wrap">
            <CodeInput value={verifyCode} onChange={onVerifyCodeChange} disabled={verifyLoading} />
          </div>
          <div className="email-center-verify-actions">
            <button
              type="submit"
              className="auth-form-submit account-action-primary email-center-verify-submit"
              disabled={verifyLoading || verifyCode.length !== 6}
            >
              {verifyLoading ? <><span className="auth-spinner" /> Submitting...</> : 'Submit code'}
            </button>
            <div className="email-center-verify-secondary-row">
              <button
                type="button"
                className="email-center-btn verify email-center-verify-secondary-btn"
                disabled={resendLoading}
                onClick={() => onResend(phone.id)}
              >
                {resendLoading ? 'Sending...' : 'Resend Code'}
              </button>
              <button
                type="button"
                className="email-center-btn delete email-center-verify-secondary-btn"
                onClick={onCancelVerify}
              >
                Cancel
              </button>
            </div>
          </div>
        </form>
        {verifyError ? (
          <div className="email-center-verify-alert">
            <StatusAlert tone="error" message={verifyError} />
          </div>
        ) : null}
      </div>
    ) : null}
  </div>
);
