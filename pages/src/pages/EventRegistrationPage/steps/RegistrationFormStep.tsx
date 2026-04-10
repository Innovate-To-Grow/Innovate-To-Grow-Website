import type {FormEvent} from 'react';

import {VERIFICATION_CODE_PLACEHOLDER} from '../../../components/Auth';
import type {EventRegistrationOptions} from '../../../features/events/api';
import type {OrganizationType} from '../useEventRegistration';

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
  phoneRegion: string;
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
  onPhoneRegionChange: (value: string) => void;
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
  phoneRegion,
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
  onPhoneRegionChange,
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
  return (
  <form onSubmit={onSubmit}>
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
          <div className="event-reg-form-group">
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
              required
              disabled={submitting}
            />
          </div>

          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="middle-name">
              Middle Name <span className="event-reg-optional">(optional)</span>
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

          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="last-name">
              Last Name
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
          </div>
        </div>

        <div className="event-reg-form-group">
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
              required
              disabled={submitting}
            />
          )}
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
          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="secondary-email">
              Secondary Email
            </label>
            <p className="event-reg-field-hint">
              Please provide a second email address so we can reach you if needed.
            </p>
            <input
              id="secondary-email"
              type="email"
              className="event-reg-input event-reg-input--editable"
              value={attendeeSecondaryEmail}
              onChange={(e) => onSecondaryEmailChange(e.target.value)}
              placeholder="We recommend using your personal email"
              disabled={submitting}
            />
          </div>
        ) : null}

        {options.collect_phone ? (
          <div className="event-reg-form-group">
            <label className="event-reg-label" htmlFor="phone">
              Phone Number {options.verify_phone ? <span className="required-mark">*</span> : null}
            </label>
            <div className="event-reg-phone-row">
              <select
                className={`event-reg-phone-region ${!phoneVerified ? 'event-reg-input--editable' : ''}`}
                value={phoneRegion}
                onChange={(e) => onPhoneRegionChange(e.target.value)}
                disabled={phoneVerified || submitting}
              >
                {options.phone_regions.map((r) => (
                  <option key={r.code} value={r.code}>
                    +{r.code.split('-')[0]} {r.label}
                  </option>
                ))}
              </select>
              <input
                id="phone"
                type="tel"
                className={`event-reg-input ${!phoneVerified ? 'event-reg-input--editable' : ''}`}
                value={attendeePhone}
                onChange={(e) => onPhoneChange(e.target.value.replace(/\D/g, ''))}
                placeholder="Phone number"
                disabled={phoneVerified || submitting}
              />
              {options.verify_phone && !phoneVerified ? (
                <button
                  type="button"
                  className="event-reg-phone-action"
                  disabled={!attendeePhone.trim() || !!phoneError || phoneSending}
                  onClick={onSendPhoneCode}
                >
                  {phoneSending ? 'Sending...' : phoneCodeSent ? 'Resend' : 'Send Code'}
                </button>
              ) : null}
              {phoneVerified ? (
                <span className="event-reg-phone-verified">Verified</span>
              ) : null}
            </div>
            {phoneError ? (
              <p className="event-reg-field-error">{phoneError}</p>
            ) : null}
            {options.verify_phone && phoneCodeSent && !phoneVerified ? (
              <div className="event-reg-phone-code-row">
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  className="event-reg-input"
                  value={phoneCode}
                  onChange={(e) => onPhoneCodeChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder={VERIFICATION_CODE_PLACEHOLDER}
                  aria-label="6-digit verification code"
                />
                <button
                  type="button"
                  className="event-reg-phone-action"
                  disabled={phoneCode.length !== 6 || verifyingPhone}
                  onClick={onVerifyPhoneCode}
                >
                  {verifyingPhone ? 'Verifying...' : 'Verify'}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </>
    </div>

    <div className="event-reg-section-card event-reg-section-card--spaced">
      <h3 className="event-reg-section-title">Registration Details</h3>

      <div className="event-reg-form-group">
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
      </div>

      {options.questions
        .sort((left, right) => left.order - right.order)
        .map((question) => (
          <div key={question.id} className="event-reg-form-group">
            <label className="event-reg-label" htmlFor={`q-${question.id}`}>
              {question.text}
              {question.is_required ? <span className="required-mark">*</span> : null}
            </label>
            <textarea
              id={`q-${question.id}`}
              className="event-reg-input event-reg-textarea"
              value={answers[question.id] || ''}
              onChange={(event) => onAnswerChange(question.id, event.target.value)}
              required={question.is_required}
            />
          </div>
        ))}
    </div>

    <button
      type="submit"
      className="event-reg-submit"
      disabled={submitting || !selectedTicketId || (options.verify_phone && !phoneVerified) || (options.collect_phone && !!phoneError) || (attendeeOrgType === 'organization' && !attendeeOrganization.trim())}
    >
      {submitting ? <><span className="event-reg-spinner" /> Registering...</> : 'Register'}
    </button>
  </form>
  );
};
