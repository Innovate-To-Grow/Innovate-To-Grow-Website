import type {FormEvent} from 'react';
import {CodeInput} from '../forms/CodeInput';
import {StatusAlert} from '../shared/StatusAlert';
import type {ContactEmail} from '../../../services/auth';

interface ContactEmailCardProps {
  contact: ContactEmail;
  verifyingId: string | null;
  verifyCode: string;
  verifyLoading: boolean;
  verifyError: string | null;
  resendLoading: boolean;
  onContactTypeChange: (contact: ContactEmail, newType: 'secondary' | 'other') => void;
  onContactSubscribeToggle: (contact: ContactEmail) => void;
  onToggleVerify: (contactId: string) => void;
  onVerifyCodeChange: (value: string) => void;
  onVerifySubmit: (event: FormEvent) => void;
  onResend: (contactId: string) => void;
  onDelete: (contactId: string) => void;
  onCancelVerify: () => void;
  onMakePrimary: (contactId: string) => void;
  makePrimaryLoadingId: string | null;
}

export const ContactEmailCard = ({
  contact,
  verifyingId,
  verifyCode,
  verifyLoading,
  verifyError,
  resendLoading,
  onContactTypeChange,
  onContactSubscribeToggle,
  onToggleVerify,
  onVerifyCodeChange,
  onVerifySubmit,
  onResend,
  onDelete,
  onCancelVerify,
  onMakePrimary,
  makePrimaryLoadingId,
}: ContactEmailCardProps) => (
  <div className="email-center-card">
    <div className="email-center-row">
      <div style={{flex: 1, minWidth: 0}}>
        <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap'}}>
          <span style={{fontWeight: 500, color: '#1f2937', wordBreak: 'break-all'}}>{contact.email_address}</span>
          <span className={`email-center-badge ${contact.verified ? 'verified' : 'unverified'}`}>
            {contact.verified ? 'Verified' : 'Unverified'}
          </span>
        </div>

        <div className="email-center-actions">
          <select
            className="email-center-type-select"
            value={contact.email_type}
            onChange={(event) => onContactTypeChange(contact, event.target.value as 'secondary' | 'other')}
          >
            <option value="secondary">Secondary</option>
            <option value="other">Other</option>
          </select>
          <label className="email-center-toggle" aria-label="Subscribe this email">
            <input type="checkbox" checked={contact.subscribe} onChange={() => onContactSubscribeToggle(contact)} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Subscribe</span>
          </label>
          {!contact.verified ? (
            <button type="button" className="email-center-btn verify" onClick={() => onToggleVerify(contact.id)}>
              Verify
            </button>
          ) : (
            <button
              type="button"
              className="email-center-btn verify"
              disabled={makePrimaryLoadingId !== null}
              onClick={() => onMakePrimary(contact.id)}
            >
              {makePrimaryLoadingId === contact.id ? 'Updating…' : 'Set as primary'}
            </button>
          )}
          <button type="button" className="email-center-btn delete" onClick={() => onDelete(contact.id)}>
            Remove
          </button>
        </div>
      </div>
    </div>

    {verifyingId === contact.id && !contact.verified ? (
      <div className="email-center-verify-inline">
        <form onSubmit={onVerifySubmit} className="email-center-verify-form">
          <CodeInput value={verifyCode} onChange={onVerifyCodeChange} disabled={verifyLoading} />
          <div className="account-action-row">
            <button
              type="submit"
              className="auth-form-submit account-action-primary"
              disabled={verifyLoading || verifyCode.length !== 6}
            >
              {verifyLoading ? <><span className="auth-spinner" /> Verifying...</> : 'Submit Code'}
            </button>
            <button
              type="button"
              className="email-center-btn verify"
              disabled={resendLoading}
              onClick={() => onResend(contact.id)}
            >
              {resendLoading ? 'Sending...' : 'Resend Code'}
            </button>
            <button
              type="button"
              className="email-center-btn delete"
              onClick={onCancelVerify}
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
