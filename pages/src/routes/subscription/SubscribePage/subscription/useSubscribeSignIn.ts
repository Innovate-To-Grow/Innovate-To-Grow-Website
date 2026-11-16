import {useState, type FormEvent} from 'react';
import {useAuth} from '@/features/auth';
import {identifyLoginInput} from '@/features/auth/components/sections/internal/identifyLoginInput';
import {getSubscribeErrorMessage} from '../steps/helpers';
import type {SubscribeWizardStep} from './types';

interface UseSubscribeSignInOptions {
  setStep: (step: SubscribeWizardStep) => void;
  setError: (message: string | null) => void;
  clearPageError: () => void;
}

/** The passwordless sign-in steps: an email or US phone number, then the code sent to it. */
export function useSubscribeSignIn({setStep, setError, clearPageError}: UseSubscribeSignInOptions) {
  const {requestEmailAuthCode, verifyEmailAuthCode, requestPhoneAuthCode, verifyPhoneAuthCode} = useAuth();
  const [email, setEmail] = useState('');
  const [identifierType, setIdentifierType] = useState<'email' | 'phone'>('email');
  // Canonical value sent to the verify/resend calls: a normalized email or 10 national digits.
  const [authValue, setAuthValue] = useState('');
  const [code, setCode] = useState('');

  // Entry accepts an email OR a US phone number; route to the matching passwordless flow.
  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = identifyLoginInput(email.trim());
    if (parsed.type === 'invalid') {
      setError('Please enter a valid email address or 10-digit US phone number.');
      return;
    }
    clearPageError();
    try {
      if (parsed.type === 'email') {
        const normalized = parsed.value.toLowerCase();
        await requestEmailAuthCode(normalized, 'subscribe');
        setIdentifierType('email');
        setAuthValue(normalized);
      } else {
        await requestPhoneAuthCode(parsed.nationalDigits, '1-US', 'subscribe');
        setIdentifierType('phone');
        setAuthValue(parsed.nationalDigits);
      }
      setStep('code');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    }
  };

  const handleCodeSubmit = async (event: FormEvent) => {
    event.preventDefault();
    clearPageError();
    try {
      const result =
        identifierType === 'phone'
          ? await verifyPhoneAuthCode(authValue, code, '1-US')
          : await verifyEmailAuthCode(authValue, code);
      setStep(result.requires_profile_completion ? 'profile' : 'manage');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    }
  };

  const handleResendCode = async () => {
    clearPageError();
    try {
      if (identifierType === 'phone') {
        await requestPhoneAuthCode(authValue, '1-US', 'subscribe');
      } else {
        await requestEmailAuthCode(authValue, 'subscribe');
      }
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    }
  };

  const handleCodeBack = () => {
    setCode('');
    clearPageError();
    setStep('email');
  };

  return {email, setEmail, code, setCode, handleEmailSubmit, handleCodeSubmit, handleResendCode, handleCodeBack};
}
