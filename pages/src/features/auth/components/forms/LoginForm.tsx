import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { getPostAuthPath } from '@/features/auth/api/redirects';
import { canSubmitNationalPhone, parsePhoneInputToNationalDigits } from '../sections/internal/phoneInput';
import { LoginEmailMode } from './LoginEmailMode';
import { LoginPasswordMode } from './LoginPasswordMode';
import { LoginPhoneMode } from './LoginPhoneMode';

type LoginMode = 'email' | 'password' | 'phone';

interface LoginFormProps {
  /** Safe internal path to return to after a successful sign-in. */
  returnTo?: string | null;
}

export const LoginForm = ({ returnTo }: LoginFormProps = {}) => {
  const {
    login,
    requestEmailAuthCode,
    requestPhoneAuthCode,
    error,
    isLoading,
    clearError,
  } = useAuth();
  const navigate = useNavigate();
  const emailInputRef = useRef<HTMLInputElement>(null);
  const phoneInputRef = useRef<HTMLInputElement>(null);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [mode, setMode] = useState<LoginMode>('email');
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const returnToParam = returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : '';

  const validateEmail = (requirePassword: boolean) => {
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
    if (!validateEmail(false)) return;
    try {
      const response = await requestEmailAuthCode(email, 'login');
      setInfoMessage(response.message);
      // Carry returnTo across the email-code step so verification lands the user back
      // on the page that sent them to log in.
      navigate(`/verify-email?flow=auth&email=${encodeURIComponent(email.trim().toLowerCase())}${returnToParam}`);
    } catch {
      // Error handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    clearError();
    if (!validateEmail(true)) return;
    try {
      const response = await login(email, password);
      navigate(getPostAuthPath(response, returnTo), { replace: true });
    } catch {
      // Error handled by context
    }
  };

  const handlePhoneSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    clearError();
    if (!canSubmitNationalPhone(phone)) {
      setValidationError('Please enter a 10-digit US phone number.');
      return;
    }
    setValidationError(null);
    try {
      const response = await requestPhoneAuthCode(phone, '1-US', 'login');
      setInfoMessage(response.message);
      navigate(`/verify-phone?phone=${encodeURIComponent(phone)}${returnToParam}`);
    } catch {
      // Error handled by context
    }
  };

  const switchMode = (next: LoginMode) => {
    setMode(next);
    setPassword('');
    clearError();
    setInfoMessage(null);
    setValidationError(null);
  };

  const clearFeedback = () => {
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

      {mode === 'password' && (
        <LoginPasswordMode
          email={email}
          password={password}
          isLoading={isLoading}
          emailInputRef={emailInputRef}
          onEmailChange={(value) => {
            setEmail(value);
            clearFeedback();
          }}
          onPasswordChange={(value) => {
            setPassword(value);
            clearError();
            setValidationError(null);
          }}
          onSubmit={handlePasswordSubmit}
          onSwitchToCode={() => switchMode('email')}
        />
      )}

      {mode === 'phone' && (
        <LoginPhoneMode
          phone={phone}
          isLoading={isLoading}
          phoneInputRef={phoneInputRef}
          onPhoneChange={(value) => {
            setPhone(parsePhoneInputToNationalDigits(value));
            clearFeedback();
          }}
          onSubmit={handlePhoneSubmit}
          onSwitchToEmail={() => switchMode('email')}
        />
      )}

      {mode === 'email' && (
        <LoginEmailMode
          email={email}
          isLoading={isLoading}
          emailInputRef={emailInputRef}
          onEmailChange={(value) => {
            setEmail(value);
            clearFeedback();
          }}
          onSubmit={handleEmailSubmit}
          onSwitchToPassword={() => switchMode('password')}
          onSwitchToPhone={() => switchMode('phone')}
        />
      )}
    </>
  );
};
