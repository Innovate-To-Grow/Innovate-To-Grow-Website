import {useState, type FormEvent} from 'react';
import {useAuth} from '@/features/auth';
import {identifyLoginInput} from '@/features/auth/components/sections/internal/identifyLoginInput';
import {getRegistrationErrorMessage, type EventRegistrationStep} from '../steps/helpers';

interface UseRegistrationSignInOptions {
  /** The event the code email links back to. */
  eventSlug: string | undefined;
  setStep: (step: EventRegistrationStep) => void;
  setError: (message: string | null) => void;
  /** The code was accepted and the member's profile is complete. */
  onSignedIn: () => Promise<void>;
  /** The code was accepted but the member must complete their profile first. */
  onProfileIncomplete: () => void;
}

/** The passwordless sign-in steps: an email or US phone number, then the code sent to it. */
export function useRegistrationSignIn({
  eventSlug,
  setStep,
  setError,
  onSignedIn,
  onProfileIncomplete,
}: UseRegistrationSignInOptions) {
  const {requestEmailAuthCode, verifyEmailAuthCode, requestPhoneAuthCode, verifyPhoneAuthCode} = useAuth();
  const [email, setEmail] = useState('');
  const [identifierType, setIdentifierType] = useState<'email' | 'phone'>('email');
  // Canonical value sent to the verify call: a trimmed email or 10 national digits.
  const [authValue, setAuthValue] = useState('');
  const [code, setCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  // Entry accepts an email OR a US phone number; route to the matching passwordless flow.
  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = identifyLoginInput(email.trim());
    if (parsed.type === 'invalid') {
      setError('Please enter a valid email address or 10-digit US phone number.');
      return;
    }
    setAuthLoading(true);
    setError(null);
    try {
      if (parsed.type === 'email') {
        await requestEmailAuthCode(parsed.value, 'event_registration', eventSlug);
        setIdentifierType('email');
        setAuthValue(parsed.value);
      } else {
        await requestPhoneAuthCode(parsed.nationalDigits, '1-US', 'event_registration');
        setIdentifierType('phone');
        setAuthValue(parsed.nationalDigits);
      }
      setStep('code');
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleCodeSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAuthLoading(true);
    setError(null);
    try {
      const result =
        identifierType === 'phone'
          ? await verifyPhoneAuthCode(authValue, code.trim(), '1-US')
          : await verifyEmailAuthCode(authValue, code.trim());
      if (result.next_step === 'complete_profile' || result.requires_profile_completion) {
        onProfileIncomplete();
        return;
      }
      setStep('loading');
      await onSignedIn();
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  return {email, setEmail, code, setCode, authLoading, handleEmailSubmit, handleCodeSubmit};
}
