import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../AuthContext';
import { getPostAuthPath } from '@/features/auth/api/redirects';
import { identifyLoginInput } from '../sections/internal/identifyLoginInput';

type LoginMode = 'identifier' | 'password';

const INVALID_IDENTIFIER = 'Please enter a valid email address or 10-digit US phone number.';

/** Why the password form cannot be submitted yet, else the identifier to sign in with. */
const passwordLoginProblem = (email: string, password: string): {error: string} | {identifier: string} => {
  const trimmedIdentifier = email.trim();
  if (!trimmedIdentifier) return {error: 'Please enter your email or phone number.'};
  const parsed = identifyLoginInput(trimmedIdentifier);
  if (parsed.type === 'invalid') return {error: INVALID_IDENTIFIER};
  if (!password) return {error: 'Please enter your password.'};
  return {identifier: parsed.type === 'phone' ? parsed.nationalDigits : parsed.value};
};

/** The sign-in form: a passwordless code by email or phone, or an email + password. */
export const useLoginForm = (returnTo: string | null | undefined) => {
  const { login, requestEmailAuthCode, requestPhoneAuthCode, clearError } = useAuth();
  const navigate = useNavigate();

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
      setValidationError(INVALID_IDENTIFIER);
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

    const problem = passwordLoginProblem(email, password);
    if ('error' in problem) {
      setValidationError(problem.error);
      return;
    }
    setValidationError(null);

    try {
      const response = await login(problem.identifier, password);
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
    // Carry over what was typed in the password form, so a visitor sent here by a lockout does not retype it.
    if (!identifier.trim() && email.trim()) {
      setIdentifier(email.trim());
    }
    setMode('identifier');
    setPassword('');
    clearFeedback();
  };

  return {
    identifier,
    setIdentifier,
    email,
    setEmail,
    password,
    setPassword,
    mode,
    infoMessage,
    validationError,
    setValidationError,
    clearFeedback,
    handleIdentifierSubmit,
    handlePasswordSubmit,
    switchToPassword,
    switchToIdentifier,
  };
};
