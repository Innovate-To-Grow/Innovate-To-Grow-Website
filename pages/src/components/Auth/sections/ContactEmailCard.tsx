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
  secondaryDisabled: boolean;
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
  secondaryDisabled,
}: ContactEmailCardProps) => (
  <div className="email-center-card">
    <div className="email-center-row">
      <div className="email-center-card-main">
        <div className="email-center-card-heading">
          <span className="email-center-card-title">{contact.email_address}</span>
          <span className={`email-center-badge ${contact.verified ? 'verified' : 'unverified'}`}>
            {contact.verified ? 'Verified' : 'Unverified'}
          </span>
        </div>

        <div className="email-center-actions">
          <select
            className="email-center-type-select"
            value={contact.email_type}
            disabled={makePrimaryLoadingId === contact.id}
            onChange={(event) => {
              const value = event.target.value;
              if (value === 'primary') {
                void onMakePrimary(contact.id);
                return;
              }
              onContactTypeChange(contact, value as 'secondary' | 'other');
            }}
            aria-label="Email role"
          >
            <option
              value="secondary"
              disabled={secondaryDisabled && contact.email_type !== 'secondary'}
              title={
                secondaryDisabled && contact.email_type !== 'secondary'
                  ? 'Another address is already set as secondary.'
                  : undefined
              }
            >
              Secondary
            </option>
            <option value="other">Other</option>
            {contact.verified ? <option value="primary">Primary</option> : null}
          </select>
          <label className="email-center-toggle" aria-label="Newsletters">
            <input type="checkbox" checked={contact.subscribe} onChange={() => onContactSubscribeToggle(contact)} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Newsletters</span>
          </label>
          {!contact.verified && verifyingId !== contact.id ? (
            <button
              type="button"
              className="email-center-btn verify"
              disabled={resendLoading}
              onClick={() => onToggleVerify(contact.id)}
            >
              Verify
            </button>
          ) : null}
          <button type="button" className="email-center-btn delete" onClick={() => onDelete(contact.id)}>
            Remove
          </button>
        </div>
      </div>
    </div>

    {verifyingId === contact.id && !contact.verified ? (
      <div className="email-center-verify-inline">
        <p className="email-center-verify-hint">
          Enter the 6-digit code we sent to this address, then tap Submit code.
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
                onClick={() => onResend(contact.id)}
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
