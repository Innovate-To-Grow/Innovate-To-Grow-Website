import type {ChangeEvent, FormEvent} from 'react';
import {StatusAlert} from '../../shared/StatusAlert';
import {Icon} from '@/components/Icon/Icon';

type OrganizationType = 'individual' | 'organization';

interface ProfileSectionProps {
  firstName: string;
  middleName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  title: string;
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
  onTitleChange: (value: string) => void;
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
  title,
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
  onTitleChange,
  onRetryProfile,
  onStartEditing,
  onCancelEditing,
}: ProfileSectionProps) => (
  <div className="itg-panel account-section account-profile-section">
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
            <span className="auth-spinner" aria-hidden />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" role="img">
              <title>Upload photo</title>
              <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" />
            </svg>
          )}
        </label>
        <input
          id="profile-image-upload"
          type="file"
          accept="image/*"
          onChange={onImageChange}
          className="sr-only profile-image-input"
          disabled={imageUploading}
        />
      </div>

      {imageError && !imageError.trim().startsWith('<') ? <p className="profile-image-error">{imageError}</p> : null}
    </div>

    {profileMessage ? <StatusAlert tone="success" message={profileMessage} /> : null}

    {profileError ? (
      <div className="auth-alert error account-profile-error">
        <Icon name="exclamation-circle" className="auth-alert-icon" />
        <span className="account-profile-error-text">{profileError}</span>
        <button
          type="button"
          className="itg-btn itg-btn-text account-retry-btn"
          onClick={onRetryProfile}
        >
          Retry
        </button>
      </div>
    ) : null}

    <form className="auth-form account-profile-form" onSubmit={onSubmit}>
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
            disabled={!isEditingProfile}
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
            disabled={!isEditingProfile}
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
            disabled={!isEditingProfile}
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
            onClick={() => onOrganizationTypeChange('organization')}
            disabled={!isEditingProfile}
          >
            Organization
          </button>
          <button
            type="button"
            className={`auth-org-toggle-btn ${organizationType === 'individual' ? 'is-active' : ''}`}
            aria-pressed={organizationType === 'individual'}
            onClick={() => onOrganizationTypeChange('individual')}
            disabled={!isEditingProfile}
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
            disabled={!isEditingProfile}
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
            disabled={!isEditingProfile}
          />
        </div>
      )}

      {isEditingProfile ? (
        <div className="account-action-row">
          <button type="submit" className="itg-btn itg-btn-primary account-action-primary" disabled={profileSaving}>
            {profileSaving ? <><span className="auth-spinner" /> Saving...</> : 'Save Profile'}
          </button>
          <button type="button" className="itg-btn itg-btn-outline account-edit-btn" onClick={onCancelEditing}>
            Cancel
          </button>
        </div>
      ) : (
        <button type="button" className="itg-btn itg-btn-outline account-edit-btn" onClick={onStartEditing}>
          Edit Profile
        </button>
      )}
    </form>
  </div>
);
