import type {ProfileSectionProps} from './types';

type ProfileImageControlProps = Pick<
  ProfileSectionProps,
  'firstName' | 'lastName' | 'profileImage' | 'imageUploading' | 'imageError' | 'onImageChange'
>;

const getInitials = (firstName: string, lastName: string) => {
  if (firstName && lastName) return `${firstName[0]}${lastName[0]}`.toUpperCase();
  return firstName ? firstName[0].toUpperCase() : 'U';
};

/** The profile photo (or initials), its upload button, and the upload error. */
export const ProfileImageControl = ({
  firstName,
  lastName,
  profileImage,
  imageUploading,
  imageError,
  onImageChange,
}: ProfileImageControlProps) => (
  <div className="profile-image-section">
    <div className="profile-image-container">
      {profileImage ? (
        <img src={profileImage} alt="Profile" className="profile-image-preview" />
      ) : (
        <div className="profile-image-placeholder">
          <span className="profile-image-initials">{getInitials(firstName, lastName)}</span>
        </div>
      )}
    </div>

    <label htmlFor="profile-image-upload" className="itg-btn itg-btn-outline profile-image-upload-btn">
      {imageUploading ? (
        <>
          <span className="auth-spinner" aria-hidden /> Uploading...
        </>
      ) : (
        <>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" />
          </svg>
          Change photo
        </>
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

    {imageError && !imageError.trim().startsWith('<') ? <p className="profile-image-error">{imageError}</p> : null}
  </div>
);
