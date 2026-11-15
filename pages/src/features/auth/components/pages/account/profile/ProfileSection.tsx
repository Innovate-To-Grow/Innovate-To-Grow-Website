import {StatusAlert} from '../../../shared/StatusAlert';
import {ProfileEditForm} from './ProfileEditForm';
import {ProfileErrorAlert} from './ProfileErrorAlert';
import {ProfileImageControl} from './ProfileImageControl';
import {ProfileSummary} from './ProfileSummary';
import type {ProfileSectionProps} from './types';

export const ProfileSection = (props: ProfileSectionProps) => {
  const {profileMessage, profileError, isEditingProfile, onRetryProfile} = props;
  return (
    <div className="itg-panel account-section account-profile-section">
      <h2 className="account-section-title">Profile Information</h2>

      <ProfileImageControl {...props} />

      {profileMessage ? <StatusAlert tone="success" message={profileMessage} /> : null}

      {profileError ? <ProfileErrorAlert message={profileError} onRetry={onRetryProfile} /> : null}

      {isEditingProfile ? <ProfileEditForm {...props} /> : <ProfileSummary {...props} />}
    </div>
  );
};
