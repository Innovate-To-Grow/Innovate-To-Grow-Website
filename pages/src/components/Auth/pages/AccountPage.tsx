import { useState, useEffect, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import {
  getProfile,
  updateProfileFields,
  changePassword,
  type ProfileResponse,
} from '../../../services/auth';
import '../Auth.css';

export const AccountPage = () => {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  // Profile state
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  // Profile form state
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [organization, setOrganization] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Password form state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordLocalErrors, setPasswordLocalErrors] = useState<Record<string, string>>({});

  // Auth guard
  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Fetch profile on mount
  useEffect(() => {
    if (!isAuthenticated) return;

    const fetchProfile = async () => {
      try {
        const data = await getProfile();
        setProfile(data);
        setFirstName(data.first_name);
        setLastName(data.last_name);
        setDisplayName(data.display_name);
        setOrganization(data.organization);
      } catch {
        setProfileError('Failed to load profile.');
      } finally {
        setProfileLoading(false);
      }
    };

    fetchProfile();
  }, [isAuthenticated]);

  const handleProfileSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setProfileSaving(true);
    setProfileMessage(null);
    setProfileError(null);

    try {
      const updated = await updateProfileFields({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        display_name: displayName.trim(),
        organization: organization.trim(),
      });
      setProfile(updated);
      setProfileMessage('Profile updated successfully.');
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setProfileError(message);
    } finally {
      setProfileSaving(false);
    }
  };

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setPasswordMessage(null);
    setPasswordError(null);

    // Client-side validation
    const errors: Record<string, string> = {};
    if (newPassword.length < 8) {
      errors.newPassword = 'Password must be at least 8 characters';
    }
    if (newPassword !== confirmPassword) {
      errors.confirmPassword = 'Passwords do not match';
    }
    setPasswordLocalErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setPasswordSaving(true);

    try {
      await changePassword(currentPassword, newPassword, confirmPassword);
      setPasswordMessage('Password changed successfully.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setPasswordError(message);
    } finally {
      setPasswordSaving(false);
    }
  };

  if (!isAuthenticated) return null;

  if (profileLoading) {
    return (
      <div className="account-page">
        <div className="account-section">
          <p style={{ textAlign: 'center', color: '#6b7280' }}>Loading profile...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="account-page">
      <h1 className="account-page-title">Account Settings</h1>

      {/* Profile Information */}
      <div className="account-section">
        <h2 className="account-section-title">Profile Information</h2>

        {profileMessage && (
          <div className="auth-alert success">
            <i className="fa fa-check-circle auth-alert-icon" />
            <span>{profileMessage}</span>
          </div>
        )}

        {profileError && (
          <div className="auth-alert error">
            <i className="fa fa-exclamation-circle auth-alert-icon" />
            <span>{profileError}</span>
          </div>
        )}

        <form className="auth-form" onSubmit={handleProfileSubmit}>
          <div className="account-form-row">
            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="account-first-name">
                First Name
              </label>
              <input
                id="account-first-name"
                type="text"
                className="auth-form-input"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                autoComplete="given-name"
              />
            </div>

            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="account-last-name">
                Last Name
              </label>
              <input
                id="account-last-name"
                type="text"
                className="auth-form-input"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name"
              />
            </div>
          </div>

          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-display-name">
              Display Name
            </label>
            <input
              id="account-display-name"
              type="text"
              className="auth-form-input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>

          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-organization">
              Organization
            </label>
            <input
              id="account-organization"
              type="text"
              className="auth-form-input"
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              placeholder="Company or organization"
              autoComplete="organization"
            />
          </div>

          <button
            type="submit"
            className="auth-form-submit"
            disabled={profileSaving}
          >
            {profileSaving ? (
              <>
                <span className="auth-spinner" />
                Saving...
              </>
            ) : (
              'Save Profile'
            )}
          </button>
        </form>
      </div>

      {/* Account Details */}
      <div className="account-section">
        <h2 className="account-section-title">Account Details</h2>

        <div className="account-readonly-group">
          <span className="auth-form-label">Email</span>
          <span className="account-readonly-value">{profile?.email}</span>
        </div>

        <div className="account-readonly-group">
          <span className="auth-form-label">Username</span>
          <span className="account-readonly-value">{profile?.username}</span>
        </div>

        <div className="account-readonly-group">
          <span className="auth-form-label">Member Since</span>
          <span className="account-readonly-value">
            {profile?.date_joined ? new Date(profile.date_joined).toLocaleDateString() : ''}
          </span>
        </div>
      </div>

      {/* Change Password */}
      <div className="account-section">
        <h2 className="account-section-title">Change Password</h2>

        {passwordMessage && (
          <div className="auth-alert success">
            <i className="fa fa-check-circle auth-alert-icon" />
            <span>{passwordMessage}</span>
          </div>
        )}

        {passwordError && (
          <div className="auth-alert error">
            <i className="fa fa-exclamation-circle auth-alert-icon" />
            <span>{passwordError}</span>
          </div>
        )}

        <form className="auth-form" onSubmit={handlePasswordSubmit}>
          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-current-password">
              Current Password
            </label>
            <input
              id="account-current-password"
              type="password"
              className="auth-form-input"
              value={currentPassword}
              onChange={(e) => {
                setCurrentPassword(e.target.value);
                setPasswordError(null);
              }}
              required
              autoComplete="current-password"
            />
          </div>

          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-new-password">
              New Password
            </label>
            <input
              id="account-new-password"
              type="password"
              className={`auth-form-input ${passwordLocalErrors.newPassword ? 'has-error' : ''}`}
              value={newPassword}
              onChange={(e) => {
                setNewPassword(e.target.value);
                setPasswordLocalErrors((prev) => ({ ...prev, newPassword: '' }));
              }}
              placeholder="At least 8 characters"
              required
              autoComplete="new-password"
              minLength={8}
            />
            {passwordLocalErrors.newPassword && (
              <span className="auth-form-error">{passwordLocalErrors.newPassword}</span>
            )}
          </div>

          <div className="auth-form-group">
            <label className="auth-form-label" htmlFor="account-confirm-password">
              Confirm New Password
            </label>
            <input
              id="account-confirm-password"
              type="password"
              className={`auth-form-input ${passwordLocalErrors.confirmPassword ? 'has-error' : ''}`}
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                setPasswordLocalErrors((prev) => ({ ...prev, confirmPassword: '' }));
              }}
              placeholder="Re-enter new password"
              required
              autoComplete="new-password"
            />
            {passwordLocalErrors.confirmPassword && (
              <span className="auth-form-error">{passwordLocalErrors.confirmPassword}</span>
            )}
          </div>

          <button
            type="submit"
            className="auth-form-submit"
            disabled={passwordSaving || !currentPassword || !newPassword || !confirmPassword}
          >
            {passwordSaving ? (
              <>
                <span className="auth-spinner" />
                Changing password...
              </>
            ) : (
              'Change Password'
            )}
          </button>
        </form>
      </div>

      {/* Sign Out */}
      <div className="account-section">
        <button
          type="button"
          className="profile-logout"
          onClick={logout}
        >
          <i className="fa fa-sign-out" style={{ marginRight: '0.5rem' }} />
          Sign Out
        </button>
      </div>
    </div>
  );
};

function getErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as { response?: { data?: Record<string, unknown> } };
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value)) {
          return value[0] as string;
        }
        if (typeof value === 'string') {
          return value;
        }
      }
    }
  }
  return 'An unexpected error occurred. Please try again.';
}
