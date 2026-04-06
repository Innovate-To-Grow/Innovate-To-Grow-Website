import type {FormEvent} from 'react';
import type {OrganizationType} from '../useEventRegistration';

interface ProfileStepProps {
  firstName: string;
  middleName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  saving: boolean;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrganizationTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export const ProfileStep = ({
  firstName,
  middleName,
  lastName,
  organizationType,
  organization,
  saving,
  onFirstNameChange,
  onMiddleNameChange,
  onLastNameChange,
  onOrganizationTypeChange,
  onOrganizationChange,
  onSubmit,
}: ProfileStepProps) => (
  <div className="event-reg-auth">
    <p className="event-reg-auth-hint">Please provide your name and organization to continue with registration.</p>
    <form onSubmit={onSubmit}>
      <div className="event-reg-form-row">
        <div className="event-reg-form-group">
          <label className="event-reg-label" htmlFor="reg-first-name">
            First Name <span className="required-mark">*</span>
          </label>
          <input
            id="reg-first-name"
            type="text"
            className="event-reg-input"
            value={firstName}
            onChange={(event) => onFirstNameChange(event.target.value)}
            placeholder="First name"
            autoComplete="given-name"
            required
            autoFocus
            disabled={saving}
          />
        </div>
        <div className="event-reg-form-group">
          <label className="event-reg-label" htmlFor="reg-middle-name">
            Middle Name <span className="event-reg-optional">(optional)</span>
          </label>
          <input
            id="reg-middle-name"
            type="text"
            className="event-reg-input"
            value={middleName}
            onChange={(event) => onMiddleNameChange(event.target.value)}
            placeholder="Middle name"
            autoComplete="additional-name"
            disabled={saving}
          />
        </div>
        <div className="event-reg-form-group">
          <label className="event-reg-label" htmlFor="reg-last-name">
            Last Name <span className="required-mark">*</span>
          </label>
          <input
            id="reg-last-name"
            type="text"
            className="event-reg-input"
            value={lastName}
            onChange={(event) => onLastNameChange(event.target.value)}
            placeholder="Last name"
            autoComplete="family-name"
            required
            disabled={saving}
          />
        </div>
      </div>
      <div className="event-reg-form-group">
        <label className="event-reg-label">
          Organization <span className="required-mark">*</span>
        </label>
        <div className="auth-org-toggle">
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'personal' ? 'is-active' : ''}`}
            onClick={() => onOrganizationTypeChange('personal')}
            disabled={saving}
          >
            Personal
          </button>
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
            onClick={() => onOrganizationTypeChange('organization')}
            disabled={saving}
          >
            Organization
          </button>
        </div>
        {organizationType === 'organization' && (
          <input
            id="reg-org"
            type="text"
            className="event-reg-input"
            value={organization}
            onChange={(event) => onOrganizationChange(event.target.value)}
            placeholder="Company or organization name"
            autoComplete="organization"
            required
            disabled={saving}
          />
        )}
      </div>
      <button
        type="submit"
        className="event-reg-submit"
        disabled={saving || !firstName.trim() || !lastName.trim() || (organizationType === 'organization' && !organization.trim())}
      >
        {saving ? <><span className="event-reg-spinner" /> Saving...</> : 'Continue'}
      </button>
    </form>
  </div>
);
