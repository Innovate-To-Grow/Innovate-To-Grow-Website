import type {FormEvent} from 'react';
import {PHONE_REGION_CHOICES} from '@/lib/phoneRegions';
import {StatusAlert} from '../shared/StatusAlert';
import {getDialCode} from './internal/helpers';
import {PhoneConsentFields} from './PhoneConsentFields';
import {
  canSubmitNationalPhone,
  formatNationalInputDisplay,
  nationalInputMaxLength,
  parsePhoneInputToNationalDigits,
} from './internal/phoneInput';

interface PhoneAddFormProps {
  addRegion: string;
  addPhoneNumber: string;
  addSubscribe: boolean;
  addTermsAccepted: boolean;
  addLoading: boolean;
  addError: string | null;
  onRegionChange: (value: string) => void;
  onPhoneNumberChange: (value: string) => void;
  onSubscribeChange: (checked: boolean) => void;
  onTermsAcceptedChange: (checked: boolean) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
}

export const PhoneAddForm = ({
  addRegion,
  addPhoneNumber,
  addSubscribe,
  addTermsAccepted,
  addLoading,
  addError,
  onRegionChange,
  onPhoneNumberChange,
  onSubscribeChange,
  onTermsAcceptedChange,
  onSubmit,
  onCancel,
}: PhoneAddFormProps) => {
  const phoneDisplay = formatNationalInputDisplay(addRegion, addPhoneNumber);
  const phonePlaceholder =
    addRegion === '1-US' || addRegion === '1-CA' ? '(555) 123-4567' : 'Enter number without country code';
  const hasPhoneNumber = addPhoneNumber.length > 0;
  const canSubmitPhone = !hasPhoneNumber || canSubmitNationalPhone(addPhoneNumber, addRegion);
  const canSubmitForm = addTermsAccepted && canSubmitPhone;

  return (
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
            inputMode="numeric"
            autoComplete="tel-national"
            maxLength={nationalInputMaxLength(addRegion)}
            value={phoneDisplay}
            onChange={(event) =>
              onPhoneNumberChange(parsePhoneInputToNationalDigits(event.target.value, addRegion))
            }
            placeholder={phonePlaceholder}
            aria-invalid={!canSubmitNationalPhone(addPhoneNumber, addRegion) && addPhoneNumber.length > 0}
            disabled={addLoading}
          />
          <p className="auth-help-text phone-add-optional-help">The phone number field is optional.</p>
        </div>
        <PhoneConsentFields
          idPrefix="add-phone"
          smsConsent={addSubscribe}
          termsAccepted={addTermsAccepted}
          disabled={addLoading}
          onSmsConsentChange={onSubscribeChange}
          onTermsAcceptedChange={onTermsAcceptedChange}
        />
        <div className="account-action-row">
          <button
            type="submit"
            className="auth-form-submit account-action-primary"
            disabled={addLoading || !canSubmitForm}
          >
            {addLoading ? (
              <>
                <span className="auth-spinner" /> Adding...
              </>
            ) : hasPhoneNumber ? (
              'Add Phone'
            ) : (
              'Save Preferences'
            )}
          </button>
          <button type="button" className="auth-form-submit account-action-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
};
