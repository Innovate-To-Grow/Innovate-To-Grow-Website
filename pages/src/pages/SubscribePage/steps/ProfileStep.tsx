import type {FormEvent} from 'react';

type OrganizationType = 'individual' | 'organization';

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
  <div className="subscribe-section">
    <p className="subscribe-hint">Complete your profile to finish subscribing.</p>
    <form onSubmit={onSubmit}>
      <div className="subscribe-form-row">
        <div className="subscribe-form-group">
          <label className="subscribe-label" htmlFor="subscribe-first-name">
            First Name <span className="subscribe-required">*</span>
          </label>
          <input
            id="subscribe-first-name"
            type="text"
            className="subscribe-input"
            value={firstName}
            onChange={(event) => onFirstNameChange(event.target.value)}
            placeholder="First name"
            autoComplete="given-name"
            required
            autoFocus
            disabled={saving}
          />
        </div>
        <div className="subscribe-form-group">
          <label className="subscribe-label" htmlFor="subscribe-middle-name">
            Middle Name <span className="subscribe-optional">(optional)</span>
          </label>
          <input
            id="subscribe-middle-name"
            type="text"
            className="subscribe-input"
            value={middleName}
            onChange={(event) => onMiddleNameChange(event.target.value)}
            placeholder="Middle name"
            autoComplete="additional-name"
            disabled={saving}
          />
        </div>
      </div>
      <div className="subscribe-form-row">
        <div className="subscribe-form-group">
          <label className="subscribe-label" htmlFor="subscribe-last-name">
            Last Name <span className="subscribe-optional">(optional)</span>
          </label>
          <input
            id="subscribe-last-name"
            type="text"
            className="subscribe-input"
            value={lastName}
            onChange={(event) => onLastNameChange(event.target.value)}
            placeholder="Last name"
            autoComplete="family-name"
            disabled={saving}
          />
        </div>
        <div className="subscribe-form-group">
          <label className="subscribe-label">Organization</label>
          <div className="subscribe-org-toggle">
            <button
              type="button"
              className={`subscribe-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
              onClick={() => onOrganizationTypeChange('individual')}
              disabled={saving}
            >
              Individual
            </button>
            <button
              type="button"
              className={`subscribe-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
              onClick={() => onOrganizationTypeChange('organization')}
              disabled={saving}
            >
              Organization
            </button>
          </div>
          {organizationType === 'organization' && (
            <input
              id="subscribe-org"
              type="text"
              className="subscribe-input"
              value={organization}
              onChange={(event) => onOrganizationChange(event.target.value)}
              placeholder="Company or organization name"
              autoComplete="organization"
              required
              disabled={saving}
            />
          )}
        </div>
      </div>
      <button type="submit" className="subscribe-submit" disabled={saving || !firstName.trim()}>
        {saving ? <><span className="subscribe-spinner" /> Saving...</> : 'Continue'}
      </button>
    </form>
  </div>
);
