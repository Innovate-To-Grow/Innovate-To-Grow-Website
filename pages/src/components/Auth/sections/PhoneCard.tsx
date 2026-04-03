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
      <div style={{flex: 1, minWidth: 0}}>
        <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap'}}>
          <span style={{fontWeight: 500, color: '#1f2937'}}>{formatPhoneDisplay(phone.phone_number, phone.region)}</span>
          <span className="email-center-badge primary">{phone.region_display}</span>
          <span className={`email-center-badge ${phone.verified ? 'verified' : 'unverified'}`}>
            {phone.verified ? 'Verified' : 'Unverified'}
          </span>
        </div>
        <div className="email-center-actions">
          <label className="email-center-toggle" aria-label="Receive notifications">
            <input type="checkbox" checked={phone.subscribe} onChange={() => onToggleSubscribe(phone)} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Notifications</span>
          </label>
          {!phone.verified ? (
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
        <form onSubmit={onVerifySubmit} className="email-center-verify-form">
          <CodeInput value={verifyCode} onChange={onVerifyCodeChange} disabled={verifyLoading} />
          <div style={{display: 'flex', gap: '0.5rem', flexWrap: 'wrap'}}>
            <button
              type="submit"
              className="auth-form-submit"
              disabled={verifyLoading || verifyCode.length !== 6}
              style={{flex: 1, marginTop: 0, fontSize: '0.875rem', padding: '0.625rem 1rem'}}
            >
              {verifyLoading ? <><span className="auth-spinner" /> Verifying...</> : 'Submit Code'}
            </button>
            <button
              type="button"
              className="email-center-btn verify"
              disabled={resendLoading}
              onClick={() => onResend(phone.id)}
              style={{fontSize: '0.8125rem'}}
            >
              {resendLoading ? 'Sending...' : 'Resend Code'}
            </button>
            <button
              type="button"
              className="email-center-btn delete"
              onClick={onCancelVerify}
              style={{fontSize: '0.8125rem'}}
            >
              Cancel
            </button>
          </div>
        </form>
        {verifyError ? <StatusAlert tone="error" message={verifyError} style={{marginTop: '0.5rem'}} /> : null}
      </div>
    ) : null}
  </div>
);
