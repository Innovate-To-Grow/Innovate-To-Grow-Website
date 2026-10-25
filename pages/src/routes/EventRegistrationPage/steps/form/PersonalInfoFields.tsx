import '@/features/auth/components/styles/orgToggle.css';
import type {FormSectionProps} from './types';

/** First, middle and last name. */
const NameFields = ({form, errors, showError, errorClass}: FormSectionProps) => (
  <div className="event-reg-form-row">
    <div className={`event-reg-form-group${errorClass(errors.missingFirstName)}`}>
      <label className="itg-label event-reg-label" htmlFor="first-name">
        First Name <span className="required-mark">*</span>
      </label>
      <input
        id="first-name"
        type="text"
        className="itg-input event-reg-input"
        value={form.attendeeFirstName}
        onChange={(e) => form.onFirstNameChange(e.target.value)}
        autoComplete="given-name"
        disabled={form.submitting}
      />
      {showError && errors.missingFirstName ? (
        <p className="event-reg-field-error">First name is required.</p>
      ) : null}
    </div>

    <div className="event-reg-form-group">
      <label className="itg-label event-reg-label" htmlFor="middle-name">
        Middle Name
      </label>
      <input
        id="middle-name"
        type="text"
        className="itg-input event-reg-input"
        value={form.attendeeMiddleName}
        onChange={(e) => form.onMiddleNameChange(e.target.value)}
        autoComplete="additional-name"
        disabled={form.submitting}
      />
    </div>

    <div className={`event-reg-form-group${errorClass(errors.missingLastName)}`}>
      <label className="itg-label event-reg-label" htmlFor="last-name">
        Last Name <span className="required-mark">*</span>
      </label>
      <input
        id="last-name"
        type="text"
        className="itg-input event-reg-input"
        value={form.attendeeLastName}
        onChange={(e) => form.onLastNameChange(e.target.value)}
        autoComplete="family-name"
        disabled={form.submitting}
      />
      {showError && errors.missingLastName ? (
        <p className="event-reg-field-error">Last name is required.</p>
      ) : null}
    </div>
  </div>
);

/** Organization or individual, the organization's name, and the attendee's title there. */
const OrganizationFields = ({form, errors, showError, errorClass}: FormSectionProps) => (
  <>
    <div className={`event-reg-form-group${errorClass(errors.missingOrganization)}`}>
      <label className="itg-label event-reg-label">
        Organization <span className="required-mark">*</span>
      </label>
      <div className="auth-org-toggle event-reg-org-toggle--editable">
        <button
          type="button"
          className={`auth-org-toggle-btn ${form.attendeeOrgType === 'organization' ? 'is-active' : ''}`}
          aria-pressed={form.attendeeOrgType === 'organization'}
          onClick={() => form.onOrgTypeChange('organization')}
          disabled={form.submitting}
        >
          Organization
        </button>
        <button
          type="button"
          className={`auth-org-toggle-btn ${form.attendeeOrgType === 'individual' ? 'is-active' : ''}`}
          aria-pressed={form.attendeeOrgType === 'individual'}
          onClick={() => form.onOrgTypeChange('individual')}
          disabled={form.submitting}
        >
          Individual
        </button>
      </div>
      {form.attendeeOrgType === 'organization' && (
        <input
          id="attendee-organization"
          type="text"
          className="itg-input event-reg-input"
          value={form.attendeeOrganization}
          onChange={(e) => form.onOrganizationChange(e.target.value)}
          placeholder="Company or organization name"
          autoComplete="organization"
          disabled={form.submitting}
        />
      )}
      {showError && errors.missingOrganization ? (
        <p className="event-reg-field-error">Organization name is required.</p>
      ) : null}
    </div>

    {form.attendeeOrgType === 'organization' && (
      <div className="event-reg-form-group">
        <label className="itg-label event-reg-label" htmlFor="attendee-title">
          Title <span className="event-reg-optional">(optional)</span>
        </label>
        <input
          id="attendee-title"
          type="text"
          className="itg-input event-reg-input"
          value={form.attendeeTitle}
          onChange={(e) => form.onTitleChange(e.target.value)}
          placeholder="Your title or position (e.g. CEO, Director)"
          autoComplete="organization-title"
          disabled={form.submitting}
        />
      </div>
    )}
  </>
);

/** Primary email (read-only), name, organization and title. */
export const PersonalInfoFields = ({form, errors, showError, errorClass}: FormSectionProps) => (
  <>
    {form.primaryEmail ? (
      <div className="event-reg-form-group">
        <label className="itg-label event-reg-label" htmlFor="primary-email">
          Primary Email
        </label>
        <input
          id="primary-email"
          type="email"
          className="itg-input event-reg-input"
          value={form.primaryEmail}
          autoComplete="email"
          disabled
        />
      </div>
    ) : null}

    <NameFields form={form} errors={errors} showError={showError} errorClass={errorClass} />

    <OrganizationFields form={form} errors={errors} showError={showError} errorClass={errorClass} />
  </>
);
