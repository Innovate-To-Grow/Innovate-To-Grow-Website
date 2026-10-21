import type {ProfileSectionProps} from './types';

type ProfileEditFormProps = Pick<
  ProfileSectionProps,
  | 'firstName'
  | 'middleName'
  | 'lastName'
  | 'organizationType'
  | 'organization'
  | 'title'
  | 'profileSaving'
  | 'onSubmit'
  | 'onFirstNameChange'
  | 'onMiddleNameChange'
  | 'onLastNameChange'
  | 'onOrganizationTypeChange'
  | 'onOrganizationChange'
  | 'onTitleChange'
  | 'onCancelEditing'
>;

const NameFields = ({
  firstName,
  middleName,
  lastName,
  onFirstNameChange,
  onMiddleNameChange,
  onLastNameChange,
}: Pick<
  ProfileEditFormProps,
  'firstName' | 'middleName' | 'lastName' | 'onFirstNameChange' | 'onMiddleNameChange' | 'onLastNameChange'
>) => (
  <div className="account-form-row">
    <div className="auth-form-group">
      <label className="itg-label auth-form-label" htmlFor="account-first-name">First Name</label>
      <input
        id="account-first-name"
        type="text"
        className="itg-input auth-form-input"
        value={firstName}
        onChange={(event) => onFirstNameChange(event.target.value)}
        autoComplete="given-name"
      />
    </div>

    <div className="auth-form-group">
      <label className="itg-label auth-form-label" htmlFor="account-middle-name">Middle Name</label>
      <input
        id="account-middle-name"
        type="text"
        className="itg-input auth-form-input"
        value={middleName}
        onChange={(event) => onMiddleNameChange(event.target.value)}
        autoComplete="additional-name"
      />
    </div>

    <div className="auth-form-group auth-form-group--full-width">
      <label className="itg-label auth-form-label" htmlFor="account-last-name">Last Name</label>
      <input
        id="account-last-name"
        type="text"
        className="itg-input auth-form-input"
        value={lastName}
        onChange={(event) => onLastNameChange(event.target.value)}
        autoComplete="family-name"
      />
    </div>
  </div>
);

/** Organization or Individual; an organization also takes its name and (optionally) the member's title. */
const OrganizationFields = ({
  organizationType,
  organization,
  title,
  onOrganizationTypeChange,
  onOrganizationChange,
  onTitleChange,
}: Pick<
  ProfileEditFormProps,
  'organizationType' | 'organization' | 'title' | 'onOrganizationTypeChange' | 'onOrganizationChange' | 'onTitleChange'
>) => (
  <>
    <div className="auth-form-group">
      <label className="itg-label auth-form-label">Organization</label>
      <div className="auth-org-toggle">
        <button
          type="button"
          className={`auth-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
          aria-pressed={organizationType === 'organization'}
          onClick={() => onOrganizationTypeChange('organization')}
        >
          Organization
        </button>
        <button
          type="button"
          className={`auth-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
          aria-pressed={organizationType === 'individual'}
          onClick={() => onOrganizationTypeChange('individual')}
        >
          Individual
        </button>
      </div>
      {organizationType === 'organization' && (
        <input
          id="account-organization"
          type="text"
          className="itg-input auth-form-input"
          value={organization}
          onChange={(event) => onOrganizationChange(event.target.value)}
          placeholder="Company or organization name"
          autoComplete="organization"
          required
        />
      )}
    </div>

    {organizationType === 'organization' && (
      <div className="auth-form-group">
        <label className="itg-label auth-form-label" htmlFor="account-title">
          Title <span className="account-label-hint">(optional)</span>
        </label>
        <input
          id="account-title"
          type="text"
          className="itg-input auth-form-input"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
          placeholder="Your title or position (e.g. CEO, Director)"
          autoComplete="organization-title"
        />
      </div>
    )}
  </>
);

/** Editing the profile: names, the organization (or Individual) and title, Save / Cancel. */
export const ProfileEditForm = (props: ProfileEditFormProps) => (
  <form className="auth-form account-profile-form" onSubmit={props.onSubmit}>
    <NameFields {...props} />
    <OrganizationFields {...props} />

    <div className="account-action-row">
      <button type="submit" className="itg-btn itg-btn-primary account-action-primary" disabled={props.profileSaving}>
        {props.profileSaving ? <><span className="auth-spinner" /> Saving...</> : 'Save Profile'}
      </button>
      <button type="button" className="itg-btn itg-btn-outline account-edit-btn" onClick={props.onCancelEditing}>
        Cancel
      </button>
    </div>
  </form>
);
