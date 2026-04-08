import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {ProfileResponse} from '../../../shared/auth/types';

interface ManageStepProps {
  profile: ProfileResponse | null;
  saving: boolean;
  onToggle: (subscribed: boolean) => Promise<void>;
}

export const ManageStep = ({profile, saving, onToggle}: ManageStepProps) => {
  const [toggled, setToggled] = useState(false);

  if (!profile) {
    return (
      <div className="subscribe-section">
        <p className="subscribe-hint">Loading subscription status...</p>
      </div>
    );
  }

  const handleToggle = async () => {
    const newValue = !profile.email_subscribe;
    await onToggle(newValue);
    setToggled(true);
  };

  return (
    <div className="subscribe-section">
      <div className="subscribe-manage-email">
        <span className="subscribe-label">Email</span>
        <span className="subscribe-manage-email-value">{profile.email}</span>
      </div>

      <div className="subscribe-manage-status">
        <span className="subscribe-manage-status-label">
          {profile.email_subscribe ? 'Subscribed' : 'Not subscribed'}
        </span>
        <button
          type="button"
          className={`subscribe-toggle ${profile.email_subscribe ? 'is-active' : ''}`}
          onClick={handleToggle}
          disabled={saving}
          aria-label={profile.email_subscribe ? 'Unsubscribe' : 'Subscribe'}
        >
          <span className="subscribe-toggle-knob" />
        </button>
      </div>

      {toggled && (
        <div className={`subscribe-alert ${profile.email_subscribe ? 'success' : 'info'}`}>
          {profile.email_subscribe
            ? 'You are now subscribed to updates and announcements.'
            : 'You have been unsubscribed from updates and announcements.'}
        </div>
      )}

      <Link to="/account" className="subscribe-link">
        View My Account
      </Link>
    </div>
  );
};
