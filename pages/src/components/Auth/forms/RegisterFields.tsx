type LocalErrors = Record<string, string>;

type OrganizationType = 'individual' | 'organization';

interface RegisterFieldsProps {
  firstName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  title: string;
  email: string;
  password: string;
  passwordConfirm: string;
  localErrors: LocalErrors;
  onFirstNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrganizationTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onPasswordConfirmChange: (value: string) => void;
}

const fieldError = (value?: string) => value ? <span className="auth-form-error">{value}</span> : null;

export const RegisterFields = ({
  firstName,
  lastName,
  organizationType,
  organization,
  title,
  email,
  password,
  passwordConfirm,
  localErrors,
  onFirstNameChange,
  onLastNameChange,
  onOrganizationTypeChange,
  onOrganizationChange,
  onTitleChange,
  onEmailChange,
  onPasswordChange,
  onPasswordConfirmChange,
}: RegisterFieldsProps) => {
  return (
    <>
      <div className="auth-form-row">
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-first-name">First Name</label>
          <input id="register-first-name" type="text" className={`auth-form-input ${localErrors.firstName ? 'has-error' : ''}`} value={firstName} onChange={(e) => onFirstNameChange(e.target.value)} placeholder="First name" required autoComplete="given-name" />
          {fieldError(localErrors.firstName)}
        </div>
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-last-name">Last Name</label>
          <input id="register-last-name" type="text" className={`auth-form-input ${localErrors.lastName ? 'has-error' : ''}`} value={lastName} onChange={(e) => onLastNameChange(e.target.value)} placeholder="Last name" required autoComplete="family-name" />
          {fieldError(localErrors.lastName)}
        </div>
      </div>

      <div className="auth-form-row">
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-email">Email</label>
          <input id="register-email" type="email" className={`auth-form-input ${localErrors.email ? 'has-error' : ''}`} value={email} onChange={(e) => onEmailChange(e.target.value)} placeholder="your@email.com" required autoComplete="email" />
          {fieldError(localErrors.email)}
        </div>
        <div className="auth-form-group">
          <label className="auth-form-label">Organization</label>
          <div className="auth-org-toggle">
            <button
              type="button"
              className={`auth-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
              onClick={() => onOrganizationTypeChange('organization')}
            >
              Organization
            </button>
            <button
              type="button"
              className={`auth-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
              onClick={() => onOrganizationTypeChange('individual')}
            >
              Individual
            </button>
          </div>
          {organizationType === 'organization' && (
            <>
              <input
                id="register-organization"
                type="text"
                className={`auth-form-input ${localErrors.organization ? 'has-error' : ''}`}
                value={organization}
                onChange={(e) => onOrganizationChange(e.target.value)}
                placeholder="Company or organization name"
                required
                autoComplete="organization"
              />
              {fieldError(localErrors.organization)}
            </>
          )}
        </div>
      </div>

      {organizationType === 'organization' && (
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-title">
            Title <span style={{ fontWeight: 400, color: '#9ca3af' }}>(optional)</span>
          </label>
          <input
            id="register-title"
            type="text"
            className="auth-form-input"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="Your title or position (e.g. CEO, Director)"
            autoComplete="organization-title"
          />
        </div>
      )}

      <div className="auth-form-row">
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-password">Password</label>
          <input id="register-password" type="password" className={`auth-form-input ${localErrors.password ? 'has-error' : ''}`} value={password} onChange={(e) => onPasswordChange(e.target.value)} placeholder="At least 8 characters" required autoComplete="new-password" minLength={8} />
          {fieldError(localErrors.password)}
        </div>
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-password-confirm">Confirm Password</label>
          <input id="register-password-confirm" type="password" className={`auth-form-input ${localErrors.passwordConfirm ? 'has-error' : ''}`} value={passwordConfirm} onChange={(e) => onPasswordConfirmChange(e.target.value)} placeholder="Re-enter your password" required autoComplete="new-password" />
          {fieldError(localErrors.passwordConfirm)}
        </div>
      </div>
    </>
  );
};
