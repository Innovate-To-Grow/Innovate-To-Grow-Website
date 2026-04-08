import type {FormEvent} from 'react';
import {StatusAlert} from '../shared/StatusAlert';

interface EmailAddFormProps {
  addEmail: string;
  addType: 'secondary' | 'other';
  addSubscribe: boolean;
  addLoading: boolean;
  addError: string | null;
  secondaryDisabled: boolean;
  onEmailChange: (value: string) => void;
  onTypeChange: (value: 'secondary' | 'other') => void;
  onSubscribeChange: (checked: boolean) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
}

export const EmailAddForm = ({
  addEmail,
  addType,
  addSubscribe,
  addLoading,
  addError,
  secondaryDisabled,
  onEmailChange,
  onTypeChange,
  onSubscribeChange,
  onSubmit,
  onCancel,
}: EmailAddFormProps) => (
  <div className="email-center-add-form">
    <h3 className="account-subsection-title">Add Connected Email</h3>
    {addError ? <StatusAlert tone="error" message={addError} style={{marginBottom: '0.75rem'}} /> : null}
    <form onSubmit={onSubmit} className="email-center-add-fields">
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="add-contact-email">Email Address</label>
        <input
          id="add-contact-email"
          type="email"
          className="auth-form-input"
          value={addEmail}
          onChange={(event) => onEmailChange(event.target.value)}
          placeholder="email@example.com"
          required
          disabled={addLoading}
        />
      </div>
      <div className="account-form-row">
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="add-contact-type">Type</label>
          <select
            id="add-contact-type"
            className="auth-form-input auth-form-select"
            value={addType}
            onChange={(event) => onTypeChange(event.target.value as 'secondary' | 'other')}
            disabled={addLoading}
          >
            <option value="secondary" disabled={secondaryDisabled}>Secondary{secondaryDisabled ? ' (already assigned)' : ''}</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div className="auth-form-group" style={{justifyContent: 'center'}}>
          <label className="email-center-toggle" style={{marginTop: '1.5rem'}}>
            <input type="checkbox" checked={addSubscribe} onChange={(event) => onSubscribeChange(event.target.checked)} disabled={addLoading} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Subscribe</span>
          </label>
        </div>
      </div>
      <div className="account-action-row">
        <button type="submit" className="auth-form-submit account-action-primary" disabled={addLoading || !addEmail.trim()}>
          {addLoading ? <><span className="auth-spinner" /> Adding...</> : 'Add & Send Verification'}
        </button>
        <button type="button" className="auth-form-submit account-action-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  </div>
);
