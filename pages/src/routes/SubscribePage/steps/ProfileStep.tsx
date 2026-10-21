import type {FormEvent, ReactNode} from 'react';

type OrganizationType = 'individual' | 'organization';

interface ProfileStepProps {
  firstName: string;
  middleName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  title: string;
  saving: boolean;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrganizationTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

const REQUIRED = <span className="subscribe-required">*</span>;
const OPTIONAL = <span className="subscribe-optional">(optional)</span>;

interface TextFieldProps {
  id: string;
  label: string;
  marker: ReactNode;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  autoComplete: string;
  saving: boolean;
  required?: boolean;
  autoFocus?: boolean;
  fullWidth?: boolean;
}

/** One labelled text input of the profile form. */
const TextField = ({
  id,
  label,
  marker,
  value,
  onChange,
  placeholder,
  autoComplete,
  saving,
  required,
  autoFocus,
  fullWidth,
}: TextFieldProps) => (
  <div className={fullWidth ? 'subscribe-form-group subscribe-form-group--full-width' : 'subscribe-form-group'}>
    <label className="itg-label subscribe-label" htmlFor={id}>
      {label} {marker}
    </label>
    <input
      id={id}
      type="text"
      className="itg-input subscribe-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      autoComplete={autoComplete}
      required={required}
      autoFocus={autoFocus}
      disabled={saving}
    />
  </div>
);

type OrganizationFieldProps = Pick<
  ProfileStepProps,
  'organizationType' | 'organization' | 'saving' | 'onOrganizationTypeChange' | 'onOrganizationChange'
>;

/** Organization or individual, and the organization's name. */
const OrganizationField = ({
  organizationType,
  organization,
  saving,
  onOrganizationTypeChange,
  onOrganizationChange,
}: OrganizationFieldProps) => (
  <div className="subscribe-form-group">
    <label className="itg-label subscribe-label">Organization</label>
    <div className="subscribe-org-toggle">
      <button
        type="button"
        className={`subscribe-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
        aria-pressed={organizationType === 'organization'}
        onClick={() => onOrganizationTypeChange('organization')}
        disabled={saving}
      >
        Organization
      </button>
      <button
        type="button"
        className={`subscribe-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
        aria-pressed={organizationType === 'individual'}
        onClick={() => onOrganizationTypeChange('individual')}
        disabled={saving}
      >
        Individual
      </button>
    </div>
    {organizationType === 'organization' && (
      <input
        id="subscribe-org"
        type="text"
        className="itg-input subscribe-input"
        value={organization}
        onChange={(event) => onOrganizationChange(event.target.value)}
        placeholder="Company or organization name"
        autoComplete="organization"
        required
        disabled={saving}
      />
    )}
  </div>
);

const canContinue = ({firstName, lastName, organizationType, organization}: ProfileStepProps) =>
  Boolean(firstName.trim() && lastName.trim() && (organizationType !== 'organization' || organization.trim()));

/** The profile a subscriber completes before managing subscriptions. */
export const ProfileStep = (props: ProfileStepProps) => {
  const {firstName, middleName, lastName, organizationType, title, saving, onSubmit} = props;
  return (
    <div className="itg-panel subscribe-section">
      <p className="subscribe-hint">Complete your profile to finish subscribing.</p>
      <form onSubmit={onSubmit}>
        <div className="subscribe-form-row">
          <TextField
            id="subscribe-first-name"
            label="First Name"
            marker={REQUIRED}
            value={firstName}
            onChange={props.onFirstNameChange}
            placeholder="First name"
            autoComplete="given-name"
            saving={saving}
            required
            autoFocus
          />
          <TextField
            id="subscribe-middle-name"
            label="Middle Name"
            marker={OPTIONAL}
            value={middleName}
            onChange={props.onMiddleNameChange}
            placeholder="Middle name"
            autoComplete="additional-name"
            saving={saving}
          />
        </div>
        <div className="subscribe-form-row">
          <TextField
            id="subscribe-last-name"
            label="Last Name"
            marker={REQUIRED}
            value={lastName}
            onChange={props.onLastNameChange}
            placeholder="Last name"
            autoComplete="family-name"
            saving={saving}
            required
          />
          <OrganizationField {...props} />
        </div>
        {organizationType === 'organization' && (
          <div className="subscribe-form-row">
            <TextField
              id="subscribe-title"
              label="Title"
              marker={OPTIONAL}
              value={title}
              onChange={props.onTitleChange}
              placeholder="Your title or position (e.g. CEO, Director)"
              autoComplete="organization-title"
              saving={saving}
              fullWidth
            />
          </div>
        )}
        <button
          type="submit"
          className="itg-btn itg-btn-primary subscribe-submit"
          disabled={saving || !canContinue(props)}
        >
          {saving ? <><span className="subscribe-spinner" /> Saving...</> : 'Continue'}
        </button>
      </form>
    </div>
  );
};
