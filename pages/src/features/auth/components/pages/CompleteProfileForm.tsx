import type { FormEvent } from 'react';

type OrganizationType = 'individual' | 'organization';

interface CompleteProfileFormProps {
  firstName: string;
  middleName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  title: string;
  isSaving: boolean;
  setFirstName: (value: string) => void;
  setMiddleName: (value: string) => void;
  setLastName: (value: string) => void;
  onOrganizationTypeChange: (value: OrganizationType) => void;
  setOrganization: (value: string) => void;
  setTitle: (value: string) => void;
  clearError: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export const CompleteProfileForm = ({
  firstName,
  middleName,
  lastName,
  organizationType,
  organization,
  title,
  isSaving,
  setFirstName,
  setMiddleName,
  setLastName,
  onOrganizationTypeChange,
  setOrganization,
  setTitle,
  clearError,
  onSubmit,
}: CompleteProfileFormProps) => {
  return (
    <form className="auth-form" onSubmit={onSubmit}>
      <div className="auth-form-row">
        <div className="auth-form-group">
          <label className="itg-label auth-form-label" htmlFor="complete-profile-first-name">
            First Name
          </label>
          <input
            id="complete-profile-first-name"
            type="text"
            className="itg-input auth-form-input"
            value={firstName}
            onChange={(event) => {
              setFirstName(event.target.value);
              clearError();
            }}
            placeholder="First name"
            autoComplete="given-name"
            required
          />
        </div>

        <div className="auth-form-group">
          <label className="itg-label auth-form-label" htmlFor="complete-profile-middle-name">
            Middle Name <span className="auth-label-hint">(optional)</span>
          </label>
          <input
            id="complete-profile-middle-name"
            type="text"
            className="itg-input auth-form-input"
            value={middleName}
            onChange={(event) => {
              setMiddleName(event.target.value);
              clearError();
            }}
            placeholder="Middle name"
            autoComplete="additional-name"
          />
        </div>

        <div className="auth-form-group">
          <label className="itg-label auth-form-label" htmlFor="complete-profile-last-name">
            Last Name
          </label>
          <input
            id="complete-profile-last-name"
            type="text"
            className="itg-input auth-form-input"
            value={lastName}
            onChange={(event) => {
              setLastName(event.target.value);
              clearError();
            }}
            placeholder="Last name"
            autoComplete="family-name"
            required
          />
        </div>
      </div>

      <div className="auth-form-group">
        <label className="itg-label auth-form-label">Organization</label>
        <div className="auth-org-toggle">
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
            aria-pressed={organizationType === 'organization'}
            onClick={() => {
              onOrganizationTypeChange('organization');
              clearError();
            }}
          >
            Organization
          </button>
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
            aria-pressed={organizationType === 'individual'}
            onClick={() => {
              onOrganizationTypeChange('individual');
              clearError();
            }}
          >
            Individual
          </button>
        </div>
        {organizationType === 'organization' && (
          <input
            id="complete-profile-organization"
            type="text"
            className="itg-input auth-form-input"
            value={organization}
            onChange={(event) => {
              setOrganization(event.target.value);
              clearError();
            }}
            placeholder="Company or organization name"
            autoComplete="organization"
            required
          />
        )}
      </div>

      {organizationType === 'organization' && (
        <div className="auth-form-group">
          <label className="itg-label auth-form-label" htmlFor="complete-profile-title">
            Title <span className="auth-label-hint">(optional)</span>
          </label>
          <input
            id="complete-profile-title"
            type="text"
            className="itg-input auth-form-input"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              clearError();
            }}
            placeholder="Your title or position (e.g. CEO, Director)"
            autoComplete="organization-title"
          />
        </div>
      )}

      <button type="submit" className="itg-btn itg-btn-primary auth-form-submit" disabled={isSaving || !firstName.trim() || !lastName.trim() || (organizationType === 'organization' && !organization.trim())}>
        {isSaving ? (
          <>
            <span className="auth-spinner" />
            Saving profile...
          </>
        ) : (
          'Continue to Account'
        )}
      </button>
    </form>
  );
};
