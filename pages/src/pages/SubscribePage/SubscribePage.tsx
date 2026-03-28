import {useState, useEffect, type FormEvent} from 'react';
import {useAuth} from '../../components/Auth';
import {updateProfileFields} from '../../services/auth';
import {CodeStep} from './steps/CodeStep';
import {DoneStep} from './steps/DoneStep';
import {EmailStep} from './steps/EmailStep';
import {getSubscribeErrorMessage, type SubscribeStep} from './steps/helpers';
import {ProfileStep} from './steps/ProfileStep';
import './SubscribePage.css';

export const SubscribePage = () => {
  const {isAuthenticated, requestEmailAuthCode, verifyEmailAuthCode, clearProfileCompletionRequirement} = useAuth();

  const [step, setStep] = useState<SubscribeStep>('email');
  const [error, setError] = useState<string | null>(null);

  // Auth state
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authFlow, setAuthFlow] = useState<string | null>(null);

  // Profile state
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [saving, setSaving] = useState(false);

  // If already authenticated, skip to profile step to set subscribe
  useEffect(() => {
    if (isAuthenticated && (step === 'email' || step === 'code')) {
      setStep('profile');
    }
  }, [isAuthenticated, step]);

  const handleEmailSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setError(null);
    try {
      const result = await requestEmailAuthCode(email.trim());
      setAuthFlow(result.flow);
      setStep('code');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleCodeSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setError(null);
    try {
      const result = await verifyEmailAuthCode(email.trim(), code.trim());
      // If existing user (login flow), go straight to subscribing
      if (result.requires_profile_completion) {
        setStep('profile');
      } else {
        // Existing user — set subscribe and done
        await updateProfileFields({email_subscribe: true});
        clearProfileCompletionRequirement();
        setStep('done');
      }
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleProfileSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!firstName.trim()) {
      setError('First name is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: organization.trim(),
        email_subscribe: true,
      });
      clearProfileCompletionRequirement();
      setStep('done');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (step === 'done') {
    return <DoneStep email={email} />;
  }

  return (
    <div className="subscribe-page">
      <h1 className="subscribe-title">Subscribe</h1>

      <div className="subscribe-info">
        <h2>Stay Updated</h2>
        <p>Subscribe to receive the latest updates and announcements. Your email will be used to create an account so you can manage your preferences.</p>
      </div>

      {error && <div className="subscribe-alert error">{error}</div>}

      {step === 'email' ? (
        <EmailStep email={email} authLoading={authLoading} onEmailChange={setEmail} onSubmit={handleEmailSubmit} />
      ) : null}

      {step === 'code' ? (
        <CodeStep
          email={email}
          code={code}
          authFlow={authFlow}
          authLoading={authLoading}
          onCodeChange={setCode}
          onSubmit={handleCodeSubmit}
          onBack={() => {
            setCode('');
            setError(null);
            setStep('email');
          }}
        />
      ) : null}

      {step === 'profile' ? (
        <ProfileStep
          firstName={firstName}
          middleName={middleName}
          lastName={lastName}
          organization={organization}
          saving={saving}
          onFirstNameChange={(value) => {
            setFirstName(value);
            setError(null);
          }}
          onMiddleNameChange={(value) => {
            setMiddleName(value);
            setError(null);
          }}
          onLastNameChange={(value) => {
            setLastName(value);
            setError(null);
          }}
          onOrganizationChange={(value) => {
            setOrganization(value);
            setError(null);
          }}
          onSubmit={handleProfileSubmit}
        />
      ) : null}
    </div>
  );
};
