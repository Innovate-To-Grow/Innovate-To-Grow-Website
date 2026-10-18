import type {FormEvent} from 'react';
import {StatusAlert} from '../shared/StatusAlert';
import {PhoneConsentFields} from './PhoneConsentFields';
import {
  canSubmitNationalPhone,
  formatNationalInputDisplay,
  nationalInputMaxLength,
  parsePhoneInputToNationalDigits,
} from './internal/phoneInput';

interface PhoneAddFormProps {
  addPhoneNumber: string;
  addSubscribe: boolean;
  addTermsAccepted: boolean;
  addLoading: boolean;
  addError: string | null;
  onPhoneNumberChange: (value: string) => void;
  onSubscribeChange: (checked: boolean) => void;
  onTermsAcceptedChange: (checked: boolean) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
}

export const PhoneAddForm = ({
  addPhoneNumber,
  addSubscribe,
  addTermsAccepted,
  addLoading,
  addError,
  onPhoneNumberChange,
  onSubscribeChange,
  onTermsAcceptedChange,
  onSubmit,
  onCancel,
}: PhoneAddFormProps) => {
  const phoneDisplay = formatNationalInputDisplay(addPhoneNumber);
  const phonePlaceholder = '(555) 123-4567';
  const hasPhoneNumber = addPhoneNumber.length > 0;
  const canSubmitPhone = !hasPhoneNumber || canSubmitNationalPhone(addPhoneNumber);
  const canSubmitForm = addTermsAccepted && canSubmitPhone;

  return (
    <div className="email-center-add-form">
      <h3 className="account-subsection-title">Add Phone Number</h3>
      {addError ? <StatusAlert tone="error" message={addError} /> : null}
      <form onSubmit={onSubmit} className="email-center-add-fields">
        <div className="auth-form-group">
          <label className="itg-label auth-form-label" htmlFor="add-phone-number">Phone Number</label>
          <input
            id="add-phone-number"
            type="tel"
            className="itg-input auth-form-input"
            inputMode="numeric"
            autoComplete="tel-national"
            maxLength={nationalInputMaxLength()}
            value={phoneDisplay}
            onChange={(event) =>
              onPhoneNumberChange(parsePhoneInputToNationalDigits(event.target.value))
            }
            placeholder={phonePlaceholder}
            aria-invalid={!canSubmitNationalPhone(addPhoneNumber) && addPhoneNumber.length > 0}
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
            className="itg-btn itg-btn-primary account-action-primary"
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
          <button type="button" className="itg-btn itg-btn-outline account-action-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
};
