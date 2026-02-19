import { useAuth } from './AuthContext';
import { LoginForm } from './LoginForm';
import { RegisterForm } from './RegisterForm';
import { VerifyPending } from './VerifyPending';
import './Auth.css';

export const AuthModal = () => {
  const { modalView, closeModal } = useAuth();

  if (!modalView || modalView === 'profile') {
    return null;
  }

  const getTitle = () => {
    switch (modalView) {
      case 'login':
        return 'Sign In';
      case 'register':
        return 'Create Account';
      case 'verify-pending':
        return 'Verify Email';
      default:
        return '';
    }
  };

  const renderContent = () => {
    switch (modalView) {
      case 'login':
        return <LoginForm />;
      case 'register':
        return <RegisterForm />;
      case 'verify-pending':
        return <VerifyPending />;
      default:
        return null;
    }
  };

  return (
    <div className="auth-modal-overlay" onClick={closeModal}>
      <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
        <div className="auth-modal-header">
          <h2 className="auth-modal-title">{getTitle()}</h2>
          <button
            type="button"
            className="auth-modal-close"
            onClick={closeModal}
            aria-label="Close"
          >
            <i className="fa fa-times" />
          </button>
        </div>

        <div className="auth-modal-body">{renderContent()}</div>
      </div>
    </div>
  );
};

