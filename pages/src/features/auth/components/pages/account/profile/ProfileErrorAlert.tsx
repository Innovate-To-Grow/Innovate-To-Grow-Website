import {Icon} from '@/components/Icon/Icon';

interface ProfileErrorAlertProps {
  message: string;
  onRetry: () => void;
}

/** A failed profile load or save, with a retry. */
export const ProfileErrorAlert = ({message, onRetry}: ProfileErrorAlertProps) => (
  <div className="auth-alert error account-profile-error">
    <Icon name="exclamation-circle" className="auth-alert-icon" />
    <span className="account-profile-error-text">{message}</span>
    <button
      type="button"
      className="itg-btn itg-btn-text account-retry-btn"
      onClick={onRetry}
    >
      Retry
    </button>
  </div>
);
