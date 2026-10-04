import {useState} from 'react';
import type {FormEvent} from 'react';

import {formatPhoneDisplay, stripPhoneFormat} from '@/lib/format';
import type {EventRegistrationOptions} from '@/features/events/api';
import type {OrganizationType} from '../useEventRegistration';
import {ContactVerificationControls} from './ContactVerificationControls';
import {getSecondaryEmailError} from './helpers';

interface RegistrationFormStepProps {
  options: EventRegistrationOptions;
  selectedTicketId: string | null;
  answers: Record<string, string>;
  submitting: boolean;
  attendeeFirstName: string;
  attendeeMiddleName: string;
  attendeeLastName: string;
  attendeeOrgType: OrganizationType;
  attendeeOrganization: string;
  attendeeTitle: string;
  attendeeSecondaryEmail: string;
  attendeePhone: string;
  primaryEmail: string;
  phoneError: string | null;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrgTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onTicketChange: (ticketId: string) => void;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSecondaryEmailChange: (value: string) => void;
  onPhoneChange: (value: string) => void;
  secondaryEmailCode: string;
  secondaryEmailCodeSent: boolean;
  secondaryEmailSending: boolean;
  secondaryEmailVerified: boolean;
  verifyingSecondaryEmail: boolean;
  onSecondaryEmailCodeChange: (value: string) => void;
  onSendSecondaryEmailCode: () => void;
  onVerifySecondaryEmailCode: () => void;
  phoneCode: string;
  phoneCodeSent: boolean;
  phoneSending: boolean;
  phoneVerified: boolean;
  verifyingPhone: boolean;
  onPhoneCodeChange: (value: string) => void;
  onSendPhoneCode: () => void;
  onVerifyPhoneCode: () => void;
  onSubmit: (event: FormEvent) => void;
}

export const RegistrationFormStep = ({
  options,
  selectedTicketId,
  answers,
  submitting,
  attendeeFirstName,
  attendeeMiddleName,
  attendeeLastName,
  attendeeOrgType,
  attendeeOrganization,
  attendeeTitle,
  attendeeSecondaryEmail,
  attendeePhone,
  primaryEmail,
  phoneError,
  onFirstNameChange,
  onMiddleNameChange,
  onLastNameChange,
  onOrgTypeChange,
  onOrganizationChange,
  onTitleChange,
  onTicketChange,
  onAnswerChange,
  onSecondaryEmailChange,
  onPhoneChange,
  secondaryEmailCode,
  secondaryEmailCodeSent,
  secondaryEmailSending,
  secondaryEmailVerified,
  verifyingSecondaryEmail,
  onSecondaryEmailCodeChange,
  onSendSecondaryEmailCode,
  onVerifySecondaryEmailCode,
  phoneCode,
  phoneCodeSent,
  phoneSending,
  phoneVerified,
  verifyingPhone,
  onPhoneCodeChange,
  onSendPhoneCode,
  onVerifyPhoneCode,
  onSubmit,
}: RegistrationFormStepProps) => {
  const [attempted, setAttempted] = useState(false);
  const [phoneFocused, setPhoneFocused] = useState(false);

  const secondaryEmailError = options.allow_secondary_email
    ? getSecondaryEmailError(attendeeSecondaryEmail, primaryEmail) : null;
  const missingSecondaryEmail = options.allow_secondary_email && options.require_secondary_email && !attendeeSecondaryEmail.trim();
  const secondaryEmailNotVerified = options.allow_secondary_email && options.verify_secondary_email && !!attendeeSecondaryEmail.trim() && !secondaryEmailVerified;

  const missingFirstName = !attendeeFirstName.trim();
  const missingLastName = !attendeeLastName.trim();
  const missingOrganization = attendeeOrgType === 'organization' && !attendeeOrganization.trim();
  const missingTicket = !selectedTicketId;
  const phoneVerificationEnabled = options.collect_phone && options.verify_phone;
  const missingPhone = options.collect_phone && options.require_phone && !attendeePhone.trim();
  const phoneNotVerified = phoneVerificationEnabled && !!attendeePhone.trim() && !phoneVerified;
  const phoneHasError = options.collect_phone && !!phoneError;
  const missingRequiredAnswers = options.questions
    .filter((q) => q.is_required)
    .filter((q) => !answers[q.id]?.trim());

  const hasErrors =
    missingFirstName ||
    missingLastName ||
    missingOrganization ||
    missingTicket ||
    missingPhone ||
    phoneNotVerified ||
    phoneHasError ||
    missingSecondaryEmail ||
    secondaryEmailNotVerified ||
    !!secondaryEmailError ||
    missingRequiredAnswers.length > 0;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (hasErrors) {
      requestAnimationFrame(() => {
        const firstError = document.querySelector('.event-reg-form-group--error');
        if (firstError && typeof firstError.scrollIntoView === 'function') {
          firstError.scrollIntoView({behavior: 'smooth', block: 'center'});
        }
      });
      return;
    }
    onSubmit(e);
  };

  const showError = attempted && !submitting;
  const errorClass = (condition: boolean) =>
    showError && condition ? ' event-reg-form-group--error' : '';

  return (
  <form onSubmit={handleSubmit} noValidate>
    <div className="event-reg-section-card">
      <div className="event-reg-section-header">
        <h3 className="event-reg-section-title">Personal Information</h3>
      </div>

      <>
        {primaryEmail ? (
          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="primary-email">
              Primary Email
            </label>
            <input
              id="primary-email"
              type="email"
              className="event-reg-input"
              value={primaryEmail}
              autoComplete="email"
              disabled
            />
          </div>
        ) : null}

        <div className="event-reg-form-row">
          <div className={`event-reg-form-group${errorClass(missingFirstName)}`}>
            <label className="event-reg-label" htmlFor="first-name">
              First Name <span className="required-mark">*</span>
            </label>
            <input
              id="first-name"
              type="text"
              className="event-reg-input event-reg-input--editable"
              value={attendeeFirstName}
              onChange={(e) => onFirstNameChange(e.target.value)}
              autoComplete="given-name"
              disabled={submitting}
            />
            {showError && missingFirstName ? (
              <p className="event-reg-field-error">First name is required.</p>
            ) : null}
          </div>

          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="middle-name">
              Middle Name
            </label>
            <input
              id="middle-name"
              type="text"
              className="event-reg-input event-reg-input--editable"
              value={attendeeMiddleName}
              onChange={(e) => onMiddleNameChange(e.target.value)}
              autoComplete="additional-name"
              disabled={submitting}
            />
          </div>

          <div className={`event-reg-form-group${errorClass(missingLastName)}`}>
            <label className="event-reg-label" htmlFor="last-name">
              Last Name <span className="required-mark">*</span>
            </label>
            <input
              id="last-name"
              type="text"
              className="event-reg-input event-reg-input--editable"
              value={attendeeLastName}
              onChange={(e) => onLastNameChange(e.target.value)}
              autoComplete="family-name"
              disabled={submitting}
            />
            {showError && missingLastName ? (
              <p className="event-reg-field-error">Last name is required.</p>
            ) : null}
          </div>
        </div>

        <div className={`event-reg-form-group${errorClass(missingOrganization)}`}>
          <label className="event-reg-label">
            Organization <span className="required-mark">*</span>
          </label>
          <div className="auth-org-toggle event-reg-org-toggle--editable">
            <button
              type="button"
              className={`auth-org-toggle-btn ${attendeeOrgType === 'organization' ? 'is-active' : ''}`}
              onClick={() => onOrgTypeChange('organization')}
              disabled={submitting}
            >
              Organization
            </button>
            <button
              type="button"
              className={`auth-org-toggle-btn ${attendeeOrgType === 'individual' ? 'is-active' : ''}`}
              onClick={() => onOrgTypeChange('individual')}
              disabled={submitting}
            >
              Individual
            </button>
          </div>
          {attendeeOrgType === 'organization' && (
            <input
              id="attendee-organization"
              type="text"
              className="event-reg-input event-reg-input--editable"
              value={attendeeOrganization}
              onChange={(e) => onOrganizationChange(e.target.value)}
              placeholder="Company or organization name"
              autoComplete="organization"
              disabled={submitting}
            />
          )}
          {showError && missingOrganization ? (
            <p className="event-reg-field-error">Organization name is required.</p>
          ) : null}
        </div>

        {attendeeOrgType === 'organization' && (
          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="attendee-title">
              Title <span className="event-reg-optional">(optional)</span>
            </label>
            <input
              id="attendee-title"
              type="text"
              className="event-reg-input event-reg-input--editable"
              value={attendeeTitle}
              onChange={(e) => onTitleChange(e.target.value)}
              placeholder="Your title or position (e.g. CEO, Director)"
              autoComplete="organization-title"
              disabled={submitting}
            />
          </div>
        )}

        {options.allow_secondary_email ? (
          <div className={`event-reg-form-group${errorClass(missingSecondaryEmail || secondaryEmailNotVerified || !!secondaryEmailError)}`}>
            <label className="event-reg-label" htmlFor="secondary-email">
              Secondary Email {options.require_secondary_email ? <span className="required-mark">*</span> : <span className="event-reg-optional">(optional)</span>}
            </label>
            <p className="event-reg-field-hint">
              Provide a second email address so we can reach you if needed.
              {options.verify_secondary_email ? ' If provided, this email must be verified.' : ''}
            </p>
            <ContactVerificationControls
              contactLabel="Secondary email"
              enabled={options.verify_secondary_email}
              hasValue={!!attendeeSecondaryEmail.trim()}
              invalid={!!secondaryEmailError}
              submitting={submitting}
              code={secondaryEmailCode}
              codeSent={secondaryEmailCodeSent}
              sending={secondaryEmailSending}
              verified={secondaryEmailVerified}
              verifying={verifyingSecondaryEmail}
              onCodeChange={onSecondaryEmailCodeChange}
              onSendCode={onSendSecondaryEmailCode}
              onVerifyCode={onVerifySecondaryEmailCode}
            >
              <input
                id="secondary-email"
                type="email"
                className="event-reg-input event-reg-input--editable"
                value={attendeeSecondaryEmail}
                onChange={(event) => onSecondaryEmailChange(event.target.value)}
                placeholder="We recommend using your personal email"
                aria-required={options.require_secondary_email}
                disabled={submitting}
              />
            </ContactVerificationControls>
            {secondaryEmailError ? <p className="event-reg-field-error">{secondaryEmailError}</p> : null}
            {showError && missingSecondaryEmail ? <p className="event-reg-field-error">Secondary email is required.</p> : null}
            {showError && secondaryEmailNotVerified && !secondaryEmailError ? (
              <p className="event-reg-field-error">Secondary email must be verified.</p>
            ) : null}
          </div>
        ) : null}

        {options.collect_phone ? (
          <div className={`event-reg-form-group${errorClass(missingPhone || phoneNotVerified || phoneHasError)}`}>
            <label className="event-reg-label" htmlFor="phone">
              Phone Number {options.require_phone ? <span className="required-mark">*</span> : <span className="event-reg-optional">(optional)</span>}
            </label>
            {phoneVerificationEnabled ? <p className="event-reg-field-hint">If provided, this phone number must be verified.</p> : null}
            <ContactVerificationControls
              contactLabel="Phone"
              enabled={phoneVerificationEnabled}
              hasValue={!!attendeePhone.trim()}
              invalid={!!phoneError}
              submitting={submitting}
              code={phoneCode}
              codeSent={phoneCodeSent}
              sending={phoneSending}
              verified={phoneVerified}
              verifying={verifyingPhone}
              onCodeChange={onPhoneCodeChange}
              onSendCode={onSendPhoneCode}
              onVerifyCode={onVerifyPhoneCode}
            >
              <input
                id="phone"
                type="tel"
                className="event-reg-input event-reg-input--editable"
                value={phoneFocused ? attendeePhone : formatPhoneDisplay(attendeePhone)}
                onChange={(event) => onPhoneChange(stripPhoneFormat(event.target.value))}
                onFocus={() => setPhoneFocused(true)}
                onBlur={() => setPhoneFocused(false)}
                placeholder="Phone number"
                aria-required={options.require_phone}
                disabled={submitting}
              />
            </ContactVerificationControls>
            {phoneError ? <p className="event-reg-field-error">{phoneError}</p> : null}
            {showError && missingPhone ? <p className="event-reg-field-error">Phone number is required.</p> : null}
            {showError && phoneNotVerified && !phoneError ? (
              <p className="event-reg-field-error">Phone number must be verified.</p>
            ) : null}
          </div>
        ) : null}
      </>
    </div>

    <div className="event-reg-section-card event-reg-section-card--spaced">
      <h3 className="event-reg-section-title">Registration Details</h3>

      <div className={`event-reg-form-group${errorClass(missingTicket)}`}>
        <label className="event-reg-label">
          Select a Ticket <span className="required-mark">*</span>
        </label>
        <div className="event-reg-tickets">
          {options.tickets.map((ticket) => (
              <label
                key={ticket.id}
                className={`event-reg-ticket-option${selectedTicketId === ticket.id ? ' selected' : ''}`}
              >
                <input
                  type="radio"
                  name="ticket"
                  value={ticket.id}
                  checked={selectedTicketId === ticket.id}
                  onChange={() => onTicketChange(ticket.id)}
                />
                <span className="event-reg-ticket-name">{ticket.name}</span>
              </label>
            ))}
        </div>
        {showError && missingTicket ? (
          <p className="event-reg-field-error">Please select a ticket.</p>
        ) : null}
      </div>

      {options.questions
        .sort((left, right) => left.order - right.order)
        .map((question) => {
          const qMissing = question.is_required && !answers[question.id]?.trim();
          return (
          <div key={question.id} className={`event-reg-form-group${errorClass(qMissing)}`}>
            <label className="event-reg-label" htmlFor={`q-${question.id}`}>
              {question.text}
              {question.is_required ? <span className="required-mark">*</span> : null}
            </label>
            <textarea
              id={`q-${question.id}`}
              className="event-reg-input event-reg-textarea"
              value={answers[question.id] || ''}
              onChange={(event) => onAnswerChange(question.id, event.target.value)}
            />
            {showError && qMissing ? (
              <p className="event-reg-field-error">This field is required.</p>
            ) : null}
          </div>
          );
        })}
    </div>

    <button
      type="submit"
      className="event-reg-submit"
      disabled={submitting}
    >
      {submitting ? <><span className="event-reg-spinner" /> Registering...</> : 'Register'}
    </button>
  </form>
  );
};
