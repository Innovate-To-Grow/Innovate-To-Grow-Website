import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { getPostAuthPath } from '@/features/auth/api/redirects';
import { identifyLoginInput } from '../sections/internal/identifyLoginInput';
import { LoginIdentifierMode } from './LoginIdentifierMode';
import { LoginPasswordMode } from './LoginPasswordMode';

type LoginMode = 'identifier' | 'password';

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
  const identifierInputRef = useRef<HTMLInputElement>(null);
  const emailInputRef = useRef<HTMLInputElement>(null);

  // `identifier` is the unified email-or-phone field; `email` is the password mode's
  // dedicated email field (password sign-in is email-only).
  const [identifier, setIdentifier] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<LoginMode>('identifier');
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const returnToParam = returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : '';

  const clearFeedback = () => {
    clearError();
    setInfoMessage(null);
    setValidationError(null);
  };

  // One input, two flows: detect whether the user typed an email or a US phone
  // number and route to the matching passwordless verification step.
  const handleIdentifierSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    clearError();

    const parsed = identifyLoginInput(identifier);
    if (parsed.type === 'invalid') {
      setValidationError('Please enter a valid email address or 10-digit US phone number.');
      return;
    }
    setValidationError(null);

    try {
      if (parsed.type === 'email') {
        const response = await requestEmailAuthCode(parsed.value, 'login');
        setInfoMessage(response.message);
        // Carry returnTo across the code step so verification lands the user back
        // on the page that sent them to log in.
        navigate(`/verify-email?flow=auth&email=${encodeURIComponent(parsed.value.toLowerCase())}${returnToParam}`);
      } else {
        const response = await requestPhoneAuthCode(parsed.nationalDigits, '1-US', 'login');
        setInfoMessage(response.message);
        navigate(`/verify-phone?phone=${encodeURIComponent(parsed.nationalDigits)}${returnToParam}`);
      }
    } catch {
      // Error handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setInfoMessage(null);
    clearError();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setValidationError('Please enter your email address.');
      return;
    }
    if (emailInputRef.current && !emailInputRef.current.validity.valid) {
      setValidationError('Please enter a valid email address.');
      return;
    }
    if (!password) {
      setValidationError('Please enter your password.');
      return;
    }
    setValidationError(null);

    try {
      const response = await login(email, password);
      navigate(getPostAuthPath(response, returnTo), { replace: true });
    } catch {
      // Error handled by context
    }
  };

  const switchToPassword = () => {
    // Prefill the password email if the unified field already holds an email.
    const parsed = identifyLoginInput(identifier);
    if (parsed.type === 'email') {
      setEmail(parsed.value);
    }
    setMode('password');
    setPassword('');
    clearFeedback();
  };

  const switchToIdentifier = () => {
    setMode('identifier');
    setPassword('');
    clearFeedback();
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

      {mode === 'password' ? (
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
          onSwitchToCode={switchToIdentifier}
        />
      ) : (
        <LoginIdentifierMode
          identifier={identifier}
          isLoading={isLoading}
          identifierInputRef={identifierInputRef}
          onIdentifierChange={(value) => {
            setIdentifier(value);
            clearFeedback();
          }}
          onSubmit={handleIdentifierSubmit}
          onSwitchToPassword={switchToPassword}
        />
      )}
    </>
  );
};
