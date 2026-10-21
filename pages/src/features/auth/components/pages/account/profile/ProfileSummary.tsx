import type {ProfileSectionProps} from './types';

type ProfileSummaryProps = Pick<
  ProfileSectionProps,
  'firstName' | 'middleName' | 'lastName' | 'organizationType' | 'organization' | 'title' | 'onStartEditing'
>;

/** The saved profile, read-only, with the Edit button. */
export const ProfileSummary = ({
  firstName,
  middleName,
  lastName,
  organizationType,
  organization,
  title,
  onStartEditing,
}: ProfileSummaryProps) => {
  const fullName = [firstName, middleName, lastName].map((part) => part.trim()).filter(Boolean).join(' ');
  return (
    <>
      <dl className="account-profile-summary">
        <div className="account-profile-summary-row">
          <dt>Name</dt>
          <dd>{fullName || 'Not set'}</dd>
        </div>
        <div className="account-profile-summary-row">
          <dt>Organization</dt>
          <dd>{organizationType === 'organization' ? organization || 'Not set' : 'Individual'}</dd>
        </div>
        {organizationType === 'organization' && title ? (
          <div className="account-profile-summary-row">
            <dt>Title</dt>
            <dd>{title}</dd>
          </div>
        ) : null}
      </dl>
      <button type="button" className="itg-btn itg-btn-outline account-edit-btn" onClick={onStartEditing}>
        Edit Profile
      </button>
    </>
  );
};
