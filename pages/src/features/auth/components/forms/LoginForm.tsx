import { useRef } from 'react';
import { useAuth } from '../AuthContext';
import {Icon} from '@/components/Icon/Icon';
import { identifyLoginInput } from '../sections/internal/identifyLoginInput';
import { LoginIdentifierMode } from './LoginIdentifierMode';
import { LoginPasswordMode } from './LoginPasswordMode';
import { useLoginForm } from './useLoginForm';

interface LoginFormProps {
  /** Safe internal path to return to after a successful sign-in. */
  returnTo?: string | null;
}

const LoginFeedback = ({infoMessage, errorMessage}: {infoMessage: string | null; errorMessage: string | null}) => (
  <>
    {infoMessage && (
      <div className="auth-alert-wrapper">
        <div className="auth-alert info" role="status">
          <Icon name="info-circle" className="auth-alert-icon" />
          <span>{infoMessage}</span>
        </div>
      </div>
    )}

    {errorMessage && (
      <div className="auth-alert-wrapper">
        <div className="auth-alert error" role="alert">
          <Icon name="exclamation-circle" className="auth-alert-icon" />
          <span>{errorMessage}</span>
        </div>
      </div>
    )}
  </>
);

export const LoginForm = ({ returnTo }: LoginFormProps = {}) => {
  const { error, isLoading, clearError } = useAuth();
  const identifierInputRef = useRef<HTMLInputElement>(null);
  const emailInputRef = useRef<HTMLInputElement>(null);
  const form = useLoginForm(returnTo);
  const {identifier, email, password, mode, clearFeedback} = form;

  return (
    <>
      <LoginFeedback infoMessage={form.infoMessage} errorMessage={form.validationError ?? error} />

      {mode === 'password' ? (
        <LoginPasswordMode
          email={email}
          password={password}
          isLoading={isLoading}
          emailInputRef={emailInputRef}
          isPhone={identifyLoginInput(email).type === 'phone'}
          onEmailChange={(value) => {
            form.setEmail(value);
            clearFeedback();
          }}
          onPasswordChange={(value) => {
            form.setPassword(value);
            clearError();
            form.setValidationError(null);
          }}
          onSubmit={form.handlePasswordSubmit}
          onSwitchToCode={form.switchToIdentifier}
        />
      ) : (
        <LoginIdentifierMode
          identifier={identifier}
          isLoading={isLoading}
          identifierInputRef={identifierInputRef}
          onIdentifierChange={(value) => {
            form.setIdentifier(value);
            clearFeedback();
          }}
          onSubmit={form.handleIdentifierSubmit}
          onSwitchToPassword={form.switchToPassword}
        />
      )}
    </>
  );
};
