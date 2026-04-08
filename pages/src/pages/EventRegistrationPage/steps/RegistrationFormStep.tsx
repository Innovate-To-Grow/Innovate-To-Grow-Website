import type {FormEvent} from 'react';
import type {EventRegistrationOptions} from '../../../features/events/api';
import type {OrganizationType} from '../useEventRegistration';

const PERSONAL_EMAIL_DOMAINS = new Set([
  'gmail.com',
  'outlook.com',
  'hotmail.com',
  'live.com',
  'msn.com',
  'yahoo.com',
  'icloud.com',
  'me.com',
  'mac.com',
  'aol.com',
  'proton.me',
  'protonmail.com',
]);

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
  attendeeSecondaryEmail: string;
  attendeePhone: string;
  primaryEmail: string;
  phoneRegion: string;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrgTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
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

const looksLikePersonalEmail = (value: string) => {
  const email = value.trim().toLowerCase();
  if (!email.includes('@')) return true;
  const domain = email.split('@')[1] || '';
  return PERSONAL_EMAIL_DOMAINS.has(domain);
};

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
  attendeeSecondaryEmail,
  attendeePhone,
  primaryEmail,
  phoneRegion,
  onFirstNameChange,
  onMiddleNameChange,
  onLastNameChange,
  onOrgTypeChange,
  onOrganizationChange,
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
  const showPersonalEmailHint = attendeeSecondaryEmail.trim() && !looksLikePersonalEmail(attendeeSecondaryEmail);

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
              className={`auth-org-toggle-btn ${attendeeOrgType === 'individual' ? 'is-active' : ''}`}
              onClick={() => onOrgTypeChange('individual')}
              disabled={submitting}
            >
              Individual
            </button>
            <button
              type="button"
              className={`auth-org-toggle-btn ${attendeeOrgType === 'organization' ? 'is-active' : ''}`}
              onClick={() => onOrgTypeChange('organization')}
              disabled={submitting}
            >
              Organization
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
            {showPersonalEmailHint ? (
              <p className="event-reg-field-warning">
                <span className="event-reg-field-warning-icon" aria-hidden>i</span>
                <span>This looks like a work or school email. We recommend using a personal email if possible.</span>
              </p>
            ) : null}
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
                  disabled={!attendeePhone.trim() || phoneSending}
                  onClick={onSendPhoneCode}
                >
                  {phoneSending ? 'Sending...' : phoneCodeSent ? 'Resend' : 'Send Code'}
                </button>
              ) : null}
              {phoneVerified ? (
                <span className="event-reg-phone-verified">Verified</span>
              ) : null}
            </div>
            {options.verify_phone && phoneCodeSent && !phoneVerified ? (
              <div className="event-reg-phone-code-row">
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  className="event-reg-input"
                  value={phoneCode}
                  onChange={(e) => onPhoneCodeChange(e.target.value.replace(/\D/g, ''))}
                  placeholder="6-digit code"
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
      disabled={submitting || !selectedTicketId || (options.verify_phone && !phoneVerified) || (attendeeOrgType === 'organization' && !attendeeOrganization.trim())}
    >
      {submitting ? <><span className="event-reg-spinner" /> Registering...</> : 'Register'}
    </button>
  </form>
  );
};
