import type {FormEvent} from 'react';
import {PHONE_REGION_CHOICES} from '../../../constants/phoneRegions';
import {StatusAlert} from '../shared/StatusAlert';
import {getDialCode} from './internal/helpers';

interface PhoneAddFormProps {
  addRegion: string;
  addPhoneNumber: string;
  addSubscribe: boolean;
  addLoading: boolean;
  addError: string | null;
  onRegionChange: (value: string) => void;
  onPhoneNumberChange: (value: string) => void;
  onSubscribeChange: (checked: boolean) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
}

export const PhoneAddForm = ({
  addRegion,
  addPhoneNumber,
  addSubscribe,
  addLoading,
  addError,
  onRegionChange,
  onPhoneNumberChange,
  onSubscribeChange,
  onSubmit,
  onCancel,
}: PhoneAddFormProps) => (
  <div className="email-center-add-form">
    <h3 className="account-subsection-title">Add Phone Number</h3>
    {addError ? <StatusAlert tone="error" message={addError} style={{marginBottom: '0.75rem'}} /> : null}
    <form onSubmit={onSubmit} className="email-center-add-fields">
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="add-phone-region">Region</label>
        <select
          id="add-phone-region"
          className="auth-form-input auth-form-select"
          value={addRegion}
          onChange={(event) => onRegionChange(event.target.value)}
          disabled={addLoading}
        >
          {PHONE_REGION_CHOICES.map((region) => (
            <option key={region.code} value={region.code}>
              {region.label} ({getDialCode(region.code)})
            </option>
          ))}
        </select>
      </div>
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="add-phone-number">Phone Number</label>
        <input
          id="add-phone-number"
          type="tel"
          className="auth-form-input"
          value={addPhoneNumber}
          onChange={(event) => onPhoneNumberChange(event.target.value)}
          placeholder="(555) 123-4567"
          required
          disabled={addLoading}
        />
      </div>
      <div className="auth-form-group" style={{justifyContent: 'center'}}>
        <label className="email-center-toggle" style={{marginTop: '0.25rem'}} aria-label="Allow SMS Messages">
          <input type="checkbox" checked={addSubscribe} onChange={(event) => onSubscribeChange(event.target.checked)} disabled={addLoading} />
          <span className="email-center-toggle-slider" />
          <span className="email-center-toggle-label">Allow SMS Messages</span>
        </label>
      </div>
      <div className="account-action-row">
        <button type="submit" className="auth-form-submit account-action-primary" disabled={addLoading || !addPhoneNumber.trim()}>
          {addLoading ? <><span className="auth-spinner" /> Adding...</> : 'Add Phone'}
        </button>
        <button type="button" className="auth-form-submit account-action-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  </div>
);
