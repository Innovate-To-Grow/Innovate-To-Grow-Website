import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { LoginEmailMode } from './LoginEmailMode';
import { LoginPasswordMode } from './LoginPasswordMode';

export const LoginForm = () => {
  const {
    login,
    requestEmailAuthCode,
    requiresProfileCompletion,
    error,
    isLoading,
    clearError,
  } = useAuth();
  const navigate = useNavigate();
  const emailInputRef = useRef<HTMLInputElement>(null);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const validateForm = (requirePassword: boolean) => {
    const trimmedEmail = email.trim();
    const emailInput = emailInputRef.current;

    if (!trimmedEmail) {
      setValidationError('Please enter your email address.');
      return false;
    }

    if (emailInput && !emailInput.validity.valid) {
      setValidationError('Please enter a valid email address.');
      return false;
    }

    if (requirePassword && !password) {
      setValidationError('Please enter your password.');
      return false;
    }

    setValidationError(null);
    return true;
  };

  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    clearError();
    if (!validateForm(false)) return;
    try {
      const response = await requestEmailAuthCode(email);
      setInfoMessage(response.message);
      navigate(`/verify-email?flow=auth&email=${encodeURIComponent(email.trim().toLowerCase())}`);
    } catch {
      // Error handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    clearError();
    if (!validateForm(true)) return;
    try {
      await login(email, password);
      navigate(requiresProfileCompletion ? '/complete-profile' : '/account', { replace: true });
    } catch {
      // Error handled by context
    }
  };

  const switchMode = (toPassword: boolean) => {
    setShowPasswordForm(toPassword);
    setPassword('');
    clearError();
    setInfoMessage(null);
    setValidationError(null);
  };

  return (
    <>
      {infoMessage && (
        <div className="auth-alert-wrapper">
          <div className="auth-alert info" role="status">
            <i className="fa fa-info-circle auth-alert-icon" aria-hidden />
            <span>{infoMessage}</span>
          </div>
        </div>
      )}

      {(validationError || error) && (
        <div className="auth-alert-wrapper">
          <div className="auth-alert error" role="alert">
            <i className="fa fa-exclamation-circle auth-alert-icon" aria-hidden />
            <span>{validationError ?? error}</span>
          </div>
        </div>
      )}

      {showPasswordForm ? (
        <LoginPasswordMode
          email={email}
          password={password}
          isLoading={isLoading}
          emailInputRef={emailInputRef}
          onEmailChange={(value) => {
            setEmail(value);
            clearError();
            setInfoMessage(null);
            setValidationError(null);
          }}
          onPasswordChange={(value) => {
            setPassword(value);
            clearError();
            setValidationError(null);
          }}
          onSubmit={handlePasswordSubmit}
          onSwitchToCode={() => switchMode(false)}
        />
      ) : (
        <LoginEmailMode
          email={email}
          isLoading={isLoading}
          emailInputRef={emailInputRef}
          onEmailChange={(value) => {
            setEmail(value);
            clearError();
            setInfoMessage(null);
            setValidationError(null);
          }}
          onSubmit={handleEmailSubmit}
          onSwitchToPassword={() => switchMode(true)}
        />
      )}
    </>
  );
};
