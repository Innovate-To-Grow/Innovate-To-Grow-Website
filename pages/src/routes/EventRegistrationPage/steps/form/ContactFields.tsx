import {useState} from 'react';
import {formatPhoneDisplay, stripPhoneFormat} from '@/lib/format';
import {ContactVerificationControls} from '../ContactVerificationControls';
import type {FormSectionProps} from './types';

/** The optional secondary email, with its verification code when the event verifies it. */
export const SecondaryEmailField = ({form, errors, showError, errorClass}: FormSectionProps) =>
  form.options.allow_secondary_email ? (
    <div className={`event-reg-form-group${errorClass(errors.missingSecondaryEmail || errors.secondaryEmailNotVerified || !!errors.secondaryEmailError)}`}>
      <label className="itg-label event-reg-label" htmlFor="secondary-email">
        Secondary Email {form.options.require_secondary_email ? <span className="required-mark">*</span> : <span className="event-reg-optional">(optional)</span>}
      </label>
      <p className="event-reg-field-hint">
        Provide a second email address so we can reach you if needed.
        {form.options.verify_secondary_email ? ' If provided, this email must be verified.' : ''}
      </p>
      <ContactVerificationControls
        contactLabel="Secondary email"
        enabled={form.options.verify_secondary_email}
        hasValue={!!form.attendeeSecondaryEmail.trim()}
        invalid={!!errors.secondaryEmailError}
        submitting={form.submitting}
        code={form.secondaryEmailCode}
        codeSent={form.secondaryEmailCodeSent}
        sending={form.secondaryEmailSending}
        verified={form.secondaryEmailVerified}
        verifying={form.verifyingSecondaryEmail}
        onCodeChange={form.onSecondaryEmailCodeChange}
        onSendCode={form.onSendSecondaryEmailCode}
        onVerifyCode={form.onVerifySecondaryEmailCode}
      >
        <input
          id="secondary-email"
          type="email"
          className="itg-input event-reg-input"
          value={form.attendeeSecondaryEmail}
          onChange={(event) => form.onSecondaryEmailChange(event.target.value)}
          placeholder="We recommend using your personal email"
          aria-required={form.options.require_secondary_email}
          disabled={form.submitting}
        />
      </ContactVerificationControls>
      {errors.secondaryEmailError ? <p className="event-reg-field-error">{errors.secondaryEmailError}</p> : null}
      {showError && errors.missingSecondaryEmail ? <p className="event-reg-field-error">Secondary email is required.</p> : null}
      {showError && errors.secondaryEmailNotVerified && !errors.secondaryEmailError ? (
        <p className="event-reg-field-error">Secondary email must be verified.</p>
      ) : null}
    </div>
  ) : null;

/** The phone number, shown formatted except while it is being edited. */
export const PhoneField = ({form, errors, showError, errorClass}: FormSectionProps) => {
  const [phoneFocused, setPhoneFocused] = useState(false);
  return (
    form.options.collect_phone ? (
      <div className={`event-reg-form-group${errorClass(errors.missingPhone || errors.phoneNotVerified || errors.phoneHasError)}`}>
        <label className="itg-label event-reg-label" htmlFor="phone">
          Phone Number {form.options.require_phone ? <span className="required-mark">*</span> : <span className="event-reg-optional">(optional)</span>}
        </label>
        {form.options.collect_phone && form.options.verify_phone ? <p className="event-reg-field-hint">If provided, this phone number must be verified.</p> : null}
        <ContactVerificationControls
          contactLabel="Phone"
          enabled={form.options.collect_phone && form.options.verify_phone}
          hasValue={!!form.attendeePhone.trim()}
          invalid={!!form.phoneError}
          submitting={form.submitting}
          code={form.phoneCode}
          codeSent={form.phoneCodeSent}
          sending={form.phoneSending}
          verified={form.phoneVerified}
          verifying={form.verifyingPhone}
          onCodeChange={form.onPhoneCodeChange}
          onSendCode={form.onSendPhoneCode}
          onVerifyCode={form.onVerifyPhoneCode}
        >
          <input
            id="phone"
            type="tel"
            className="itg-input event-reg-input"
            value={phoneFocused ? form.attendeePhone : formatPhoneDisplay(form.attendeePhone)}
            onChange={(event) => form.onPhoneChange(stripPhoneFormat(event.target.value))}
            onFocus={() => setPhoneFocused(true)}
            onBlur={() => setPhoneFocused(false)}
            placeholder="Phone number"
            aria-required={form.options.require_phone}
            disabled={form.submitting}
          />
        </ContactVerificationControls>
        {form.phoneError ? <p className="event-reg-field-error">{form.phoneError}</p> : null}
        {showError && errors.missingPhone ? <p className="event-reg-field-error">Phone number is required.</p> : null}
        {showError && errors.phoneNotVerified && !form.phoneError ? (
          <p className="event-reg-field-error">Phone number must be verified.</p>
        ) : null}
      </div>
    ) : null
  );
};
