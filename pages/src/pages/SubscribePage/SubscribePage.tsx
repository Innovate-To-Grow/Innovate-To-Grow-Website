import {useEffect, useState, type FormEvent} from 'react';
import {useAuth} from '../../components/Auth';
import {getProfile, updateProfileFields} from '../../services/auth';
import type {ProfileResponse} from '../../shared/auth/types';
import {CodeStep} from './steps/CodeStep';
import {EmailStep} from './steps/EmailStep';
import {ManageStep} from './steps/ManageStep';
import {ProfileStep} from './steps/ProfileStep';
import {getSubscribeErrorMessage} from './steps/helpers';

type Step = 'email' | 'code' | 'profile' | 'manage';
type OrganizationType = 'individual' | 'organization';

export const SubscribePage = () => {
  const {isAuthenticated, isLoading, requestEmailAuthCode, verifyEmailAuthCode, clearError} = useAuth();

  const [step, setStep] = useState<Step>(() => (isAuthenticated ? 'manage' : 'email'));
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationType, setOrganizationType] = useState<OrganizationType>('organization');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);

  // When auth state changes to authenticated, jump to manage
  useEffect(() => {
    if (isAuthenticated && step !== 'manage' && step !== 'profile') {
      setStep('manage');
    }
  }, [isAuthenticated, step]);

  // Fetch profile when entering manage step
  useEffect(() => {
    if (step === 'manage' && isAuthenticated) {
      getProfile()
        .then(setProfile)
        .catch(() => setError('Failed to load subscription status.'));
    }
  }, [step, isAuthenticated]);

  const clearPageError = () => {
    setError(null);
    clearError();
  };

  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    clearPageError();
    try {
      await requestEmailAuthCode(email.trim().toLowerCase());
      setStep('code');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    }
  };

  const handleCodeSubmit = async (event: FormEvent) => {
    event.preventDefault();
    clearPageError();
    try {
      const result = await verifyEmailAuthCode(email.trim().toLowerCase(), code);
      if (result.requires_profile_completion) {
        setStep('profile');
      } else {
        setStep('manage');
      }
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    }
  };

  const handleResendCode = async () => {
    clearPageError();
    try {
      await requestEmailAuthCode(email.trim().toLowerCase());
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    }
  };

  const handleCodeBack = () => {
    setCode('');
    clearPageError();
    setStep('email');
  };

  const handleProfileSubmit = async (event: FormEvent) => {
    event.preventDefault();
    clearPageError();
    setSaving(true);
    try {
      const orgValue = organizationType === 'individual' ? 'Individual' : organization.trim();
      const titleValue = organizationType === 'organization' ? title.trim() : '';
      const updated = await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: orgValue,
        title: titleValue,
        email_subscribe: true,
      });
      setProfile(updated);
      setStep('manage');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleSubscriptionToggle = async (subscribed: boolean) => {
    clearPageError();
    setSaving(true);
    try {
      const updated = await updateProfileFields({email_subscribe: subscribed});
      setProfile(updated);
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="subscribe-page">
      <h1 className="subscribe-title">Newsletter</h1>

      <div className="subscribe-info">
        <h2>Stay Updated</h2>
        <p>
          {step === 'manage'
            ? 'Manage your email subscription preferences below.'
            : 'Subscribe to receive updates and announcements from Innovate to Grow.'}
        </p>
        {step === 'manage' ? (
          <p className="subscribe-info-note">
            This newsletter setting does not affect I2G event emails or account-related notifications—you will still
            receive those when applicable.
          </p>
        ) : null}
      </div>

      {error && <div className="subscribe-alert error">{error}</div>}

      {step === 'email' && (
        <EmailStep
          email={email}
          authLoading={isLoading}
          onEmailChange={(value) => {
            setEmail(value);
            clearPageError();
          }}
          onSubmit={handleEmailSubmit}
        />
      )}

      {step === 'code' && (
        <CodeStep
          email={email}
          code={code}
          authLoading={isLoading}
          onCodeChange={(value) => {
            setCode(value);
            clearPageError();
          }}
          onSubmit={handleCodeSubmit}
          onBack={handleCodeBack}
          onResend={handleResendCode}
        />
      )}

      {step === 'profile' && (
        <ProfileStep
          firstName={firstName}
          middleName={middleName}
          lastName={lastName}
          organizationType={organizationType}
          organization={organization}
          saving={saving}
          onFirstNameChange={(value) => {
            setFirstName(value);
            clearPageError();
          }}
          onMiddleNameChange={(value) => {
            setMiddleName(value);
            clearPageError();
          }}
          onLastNameChange={(value) => {
            setLastName(value);
            clearPageError();
          }}
          onOrganizationTypeChange={(value) => {
            setOrganizationType(value);
            setOrganization('');
            setTitle('');
            clearPageError();
          }}
          onOrganizationChange={(value) => {
            setOrganization(value);
            clearPageError();
          }}
          title={title}
          onTitleChange={(value) => {
            setTitle(value);
            clearPageError();
          }}
          onSubmit={handleProfileSubmit}
        />
      )}

      {step === 'manage' && (
        <ManageStep
          profile={profile}
          saving={saving}
          onToggle={handleSubscriptionToggle}
        />
      )}
    </div>
  );
};
