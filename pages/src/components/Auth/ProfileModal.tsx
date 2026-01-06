import { useState, type FormEvent, useEffect } from 'react';
import { useAuth } from './AuthContext';
import './Auth.css';

export const ProfileModal = () => {
  const { user, updateDisplayName, logout, error, isLoading, closeModal, clearError } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (user?.display_name) {
      setDisplayName(user.display_name);
    }
  }, [user?.display_name]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);

    try {
      await updateDisplayName(displayName);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      // Error is handled by context
    }
  };

  const handleLogout = () => {
    logout();
  };

  if (!user) return null;

  return (
    <div className="auth-modal-overlay" onClick={closeModal}>
      <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
        <div className="auth-modal-header">
          <h2 className="auth-modal-title">Profile</h2>
          <button
            type="button"
            className="auth-modal-close"
            onClick={closeModal}
            aria-label="Close"
          >
            <i className="fa fa-times" />
          </button>
        </div>

        <div className="auth-modal-body">
          <div className="profile-email">
            <strong>Email:</strong> {user.email}
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            {error && (
              <div className="auth-alert error">
                <i className="fa fa-exclamation-circle auth-alert-icon" />
                <span>{error}</span>
              </div>
            )}

            {saved && (
              <div className="auth-alert success">
                <i className="fa fa-check-circle auth-alert-icon" />
                <span>Profile updated successfully!</span>
              </div>
            )}

            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="profile-display-name">
                Display Name
              </label>
              <input
                id="profile-display-name"
                type="text"
                className="auth-form-input"
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value);
                  clearError();
                  setSaved(false);
                }}
                placeholder="Enter a display name"
                maxLength={255}
              />
            </div>

            <button
              type="submit"
              className="auth-form-submit"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <span className="auth-spinner" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </button>
          </form>

          <button
            type="button"
            className="profile-logout"
            onClick={handleLogout}
          >
            <i className="fa fa-sign-out" style={{ marginRight: '0.5rem' }} />
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
};

