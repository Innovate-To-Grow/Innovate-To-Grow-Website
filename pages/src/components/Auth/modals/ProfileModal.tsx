import { useAuth } from '../AuthContext';
import '../Auth.css';

export const ProfileModal = () => {
  const { user, logout, closeModal } = useAuth();

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
          <div className="profile-email">
            <strong>Name:</strong> {user.display_name || user.username}
          </div>

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
    </div>
  );
};
