import type {ChangeEvent, FormEvent} from 'react';
import {StatusAlert} from '../../shared/StatusAlert';

type OrganizationType = 'individual' | 'organization';

interface ProfileSectionProps {
  firstName: string;
  middleName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  profileImage: string | null;
  imageUploading: boolean;
  imageError: string | null;
  profileSaving: boolean;
  profileMessage: string | null;
  profileError: string | null;
  isEditingProfile: boolean;
  onImageChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmit: (event: FormEvent) => void;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrganizationTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onRetryProfile: () => void;
  onStartEditing: () => void;
  onCancelEditing: () => void;
}

const getInitials = (firstName: string, lastName: string) => {
  if (firstName && lastName) return `${firstName[0]}${lastName[0]}`.toUpperCase();
  return firstName ? firstName[0].toUpperCase() : 'U';
};

export const ProfileSection = ({
  firstName,
  middleName,
  lastName,
  organizationType,
  organization,
  profileImage,
  imageUploading,
  imageError,
  profileSaving,
  profileMessage,
  profileError,
  isEditingProfile,
  onImageChange,
  onSubmit,
  onFirstNameChange,
  onMiddleNameChange,
  onLastNameChange,
  onOrganizationTypeChange,
  onOrganizationChange,
  onRetryProfile,
  onStartEditing,
  onCancelEditing,
}: ProfileSectionProps) => (
  <div className="account-section account-profile-section">
    <h2 className="account-section-title">Profile Information</h2>

    <div className="profile-image-section">
      <div className="profile-image-container">
        {profileImage ? (
          <img src={profileImage} alt="Profile" className="profile-image-preview" />
        ) : (
          <div className="profile-image-placeholder">
            <span className="profile-image-initials">{getInitials(firstName, lastName)}</span>
          </div>
        )}

        <label htmlFor="profile-image-upload" className="profile-image-upload-btn" aria-label="Upload photo">
          {imageUploading ? (
            <i className="fa fa-spinner fa-spin" aria-hidden />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" />
            </svg>
          )}
        </label>
        <input
          id="profile-image-upload"
          type="file"
          accept="image/*"
          onChange={onImageChange}
          style={{display: 'none'}}
          disabled={imageUploading}
        />
      </div>

      {imageError && !imageError.trim().startsWith('<') ? <p className="profile-image-error">{imageError}</p> : null}
    </div>

    {profileMessage ? <StatusAlert tone="success" message={profileMessage} /> : null}

    {profileError ? (
      <div className="auth-alert error" style={{flexWrap: 'wrap', gap: '0.5rem'}}>
        <i className="fa fa-exclamation-circle auth-alert-icon" aria-hidden />
        <span style={{flex: 1, minWidth: 0}}>{profileError}</span>
        <button
          type="button"
          className="auth-verify-resend"
          style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem', flexShrink: 0}}
          onClick={onRetryProfile}
        >
          Retry
        </button>
      </div>
    ) : null}

    <form className="auth-form account-profile-form" onSubmit={onSubmit}>
      <div className="account-form-row">
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="account-first-name">First Name</label>
          <input
            id="account-first-name"
            type="text"
            className="auth-form-input"
            value={firstName}
            onChange={(event) => onFirstNameChange(event.target.value)}
            autoComplete="given-name"
            disabled={!isEditingProfile}
          />
        </div>

        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="account-middle-name">Middle Name</label>
          <input
            id="account-middle-name"
            type="text"
            className="auth-form-input"
            value={middleName}
            onChange={(event) => onMiddleNameChange(event.target.value)}
            autoComplete="additional-name"
            disabled={!isEditingProfile}
          />
        </div>

        <div className="auth-form-group auth-form-group--full-width">
          <label className="auth-form-label" htmlFor="account-last-name">Last Name</label>
          <input
            id="account-last-name"
            type="text"
            className="auth-form-input"
            value={lastName}
            onChange={(event) => onLastNameChange(event.target.value)}
            autoComplete="family-name"
            disabled={!isEditingProfile}
          />
        </div>
      </div>

      <div className="auth-form-group">
        <label className="auth-form-label">Organization</label>
        <div className="auth-org-toggle">
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
            onClick={() => onOrganizationTypeChange('individual')}
            disabled={!isEditingProfile}
          >
            Individual
          </button>
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'organization' ? 'is-active' : ''}`}
            onClick={() => onOrganizationTypeChange('organization')}
            disabled={!isEditingProfile}
          >
            Organization
          </button>
        </div>
        {organizationType === 'organization' && (
          <input
            id="account-organization"
            type="text"
            className="auth-form-input"
            value={organization}
            onChange={(event) => onOrganizationChange(event.target.value)}
            placeholder="Company or organization name"
            autoComplete="organization"
            disabled={!isEditingProfile}
            required
          />
        )}
      </div>

      {isEditingProfile ? (
        <div className="account-action-row">
          <button type="submit" className="auth-form-submit account-action-primary" disabled={profileSaving}>
            {profileSaving ? <><span className="auth-spinner" /> Saving...</> : 'Save Profile'}
          </button>
          <button type="button" className="account-edit-btn" onClick={onCancelEditing}>
            Cancel
          </button>
        </div>
      ) : (
        <button type="button" className="account-edit-btn" onClick={onStartEditing}>
          Edit Profile
        </button>
      )}
    </form>
  </div>
);
