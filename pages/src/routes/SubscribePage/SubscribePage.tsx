import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {useSearchParams} from 'react-router';
import {useAuth} from '@/features/auth';
import {
  getContactEmails,
  getContactPhones,
  getProfile,
  updateContactEmail,
  updateContactPhone,
  updateProfileFields,
} from '@/features/auth';
import {hasRequiredNameFields} from '@/features/auth/api/profileCompletion';
import {identifyLoginInput} from '@/features/auth/components/sections/internal/identifyLoginInput';
import type {ContactEmail, ContactPhone, ProfileResponse} from '@/features/auth/api/types';
import {CodeStep} from './steps/CodeStep';
import {EmailStep} from './steps/EmailStep';
import {ManageStep} from './steps/ManageStep';
import {ProfileStep} from './steps/ProfileStep';
import {getSubscribeErrorMessage} from './steps/helpers';

type Step = 'email' | 'code' | 'profile' | 'manage';
type OrganizationType = 'individual' | 'organization';
type LoadState = 'idle' | 'loading' | 'ready' | 'error';

export const SubscribePage = () => {
  const [searchParams] = useSearchParams();
  const {
    isAuthenticated,
    isLoading,
    requestEmailAuthCode,
    verifyEmailAuthCode,
    requestPhoneAuthCode,
    verifyPhoneAuthCode,
    clearError,
    clearProfileCompletionRequirement,
  } = useAuth();
  const shouldStartInProfile = searchParams.get('step') === 'profile';

  const [step, setStep] = useState<Step>(() => {
    if (!isAuthenticated) {
      return 'email';
    }
    return shouldStartInProfile ? 'profile' : 'manage';
  });
  const [email, setEmail] = useState('');
  const [identifierType, setIdentifierType] = useState<'email' | 'phone'>('email');
  // Canonical value sent to the verify/resend calls: a normalized email or 10 national digits.
  const [authValue, setAuthValue] = useState('');
  const [code, setCode] = useState('');
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationType, setOrganizationType] = useState<OrganizationType>('organization');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [profileLoadState, setProfileLoadState] = useState<LoadState>(
    () => (isAuthenticated && shouldStartInProfile ? 'loading' : 'idle'),
  );
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [contactEmails, setContactEmails] = useState<ContactEmail[]>([]);
  const [contactPhones, setContactPhones] = useState<ContactPhone[]>([]);
  const [preferencesLoadState, setPreferencesLoadState] =
    useState<LoadState>(
      () => (isAuthenticated && !shouldStartInProfile ? 'loading' : 'idle'),
    );
  const [preferencesLoadError, setPreferencesLoadError] =
    useState<string | null>(null);
  const [preferenceSavingId, setPreferenceSavingId] = useState<string | null>(null);
  const [preferenceMessage, setPreferenceMessage] = useState<string | null>(null);

  const profileRequestSequence = useRef(0);
  const preferencesRequestSequence = useRef(0);

  const applyProfileToForm = useCallback((nextProfile: ProfileResponse) => {
    setFirstName(nextProfile.first_name ?? '');
    setMiddleName(nextProfile.middle_name ?? '');
    setLastName(nextProfile.last_name ?? '');

    const org = nextProfile.organization ?? '';
    const normalized = org.trim().toLowerCase();
    const isIndividual = ['individual', 'personal'].includes(normalized);
    setOrganizationType(isIndividual ? 'individual' : 'organization');
    setOrganization(isIndividual ? '' : org);
    setTitle(nextProfile.title ?? '');
  }, []);

  // When auth state changes after verification, advance out of the email/code
  // steps, but do not override an in-progress profile or manage screen.
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    if (step === 'email' || step === 'code') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- authentication changes outside this component; advancing the wizard is synchronization with that external state.
      setStep(shouldStartInProfile ? 'profile' : 'manage');
    }
  }, [isAuthenticated, shouldStartInProfile, step]);

  const loadProfileForForm = useCallback(async () => {
    const requestId = ++profileRequestSequence.current;
    setProfileLoadState('loading');
    setProfileLoadError(null);
    try {
      const nextProfile = await getProfile();
      if (requestId !== profileRequestSequence.current) return;
      setProfile(nextProfile);
      applyProfileToForm(nextProfile);
      setProfileLoadState('ready');
    } catch {
      if (requestId !== profileRequestSequence.current) return;
      setProfileLoadError('Failed to load your profile.');
      setProfileLoadState('error');
    }
  }, [applyProfileToForm]);

  useEffect(() => {
    if (!isAuthenticated || step !== 'profile') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starting the explicit async load state is synchronization with the authenticated route step.
    void loadProfileForForm();
    return () => {
      profileRequestSequence.current += 1;
    };
  }, [step, isAuthenticated, loadProfileForForm]);

  const loadPreferences = useCallback(async () => {
    const requestId = ++preferencesRequestSequence.current;
    setPreferencesLoadState('loading');
    setPreferencesLoadError(null);
    try {
      const [nextProfile, nextContactEmails, nextContactPhones] =
        await Promise.all([
          getProfile(),
          getContactEmails(),
          getContactPhones(),
        ]);
      if (requestId !== preferencesRequestSequence.current) return;
      setProfile(nextProfile);
      setContactEmails(nextContactEmails);
      setContactPhones(nextContactPhones);
      setPreferencesLoadState('ready');
    } catch {
      if (requestId !== preferencesRequestSequence.current) return;
      setPreferencesLoadError('Failed to load subscription preferences.');
      setPreferencesLoadState('error');
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated || step !== 'manage') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starting the explicit async load state is synchronization with the authenticated route step.
    void loadPreferences();
    return () => {
      preferencesRequestSequence.current += 1;
    };
  }, [step, isAuthenticated, loadPreferences]);

  const clearPageError = () => {
    setError(null);
    setPreferenceMessage(null);
    clearError();
  };

  const getPreferenceMessage = (kind: 'email' | 'phone', subscribed: boolean) => {
    if (kind === 'phone') {
      return `Text Messages ${subscribed ? 'enabled' : 'disabled'}.`;
    }
    return `Newsletters ${subscribed ? 'enabled' : 'disabled'}.`;
  };

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
      if (hasRequiredNameFields(updated)) {
        clearProfileCompletionRequirement();
      }
      setProfile(updated);
      setStep('manage');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handlePrimaryEmailToggle = async (subscribed: boolean) => {
    clearPageError();
    setPreferenceSavingId('primary-email');
    try {
      const updated = await updateProfileFields({email_subscribe: subscribed});
      setProfile(updated);
      setPreferenceMessage(getPreferenceMessage('email', subscribed));
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setPreferenceSavingId(null);
    }
  };

  const handleContactEmailToggle = async (contact: ContactEmail, subscribed: boolean) => {
    clearPageError();
    setPreferenceSavingId(`email-${contact.id}`);
    try {
      const updated = await updateContactEmail(contact.id, {subscribe: subscribed});
      setContactEmails((current) => current.map((item) => (item.id === contact.id ? updated : item)));
      setPreferenceMessage(getPreferenceMessage('email', subscribed));
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setPreferenceSavingId(null);
    }
  };

  const handleContactPhoneToggle = async (phone: ContactPhone, subscribed: boolean) => {
    clearPageError();
    setPreferenceSavingId(`phone-${phone.id}`);
    try {
      const updated = await updateContactPhone(phone.id, {subscribe: subscribed});
      setContactPhones((current) => current.map((item) => (item.id === phone.id ? updated : item)));
      setPreferenceMessage(getPreferenceMessage('phone', subscribed));
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setPreferenceSavingId(null);
    }
  };

  return (
    <div className="subscribe-page">
      <h1 className="subscribe-title">Subscriptions</h1>

      <div className="subscribe-info">
        <h2>Stay Updated</h2>
        <p>
          {step === 'manage'
            ? 'Manage your email and text message subscription preferences below.'
            : 'Subscribe to receive updates and announcements from Innovate to Grow.'}
        </p>
        {step === 'manage' ? (
          <p className="subscribe-info-note">
            These settings do not affect I2G event emails or account-related notifications—you will still receive those
            when applicable.
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
        profileLoadState === 'ready' ? (
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
        ) : profileLoadState === 'error' ? (
          <div className="subscribe-section" role="alert">
            <p className="subscribe-hint">{profileLoadError}</p>
            <button
              type="button"
              className="subscribe-submit"
              onClick={() => void loadProfileForForm()}
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="subscribe-section" role="status">
            Loading your profile...
          </div>
        )
      )}

      {step === 'manage' && (
        preferencesLoadState === 'ready' && profile ? (
          <ManageStep
            profile={profile}
            contactEmails={contactEmails}
            contactPhones={contactPhones}
            savingId={preferenceSavingId}
            message={preferenceMessage}
            onPrimaryEmailToggle={handlePrimaryEmailToggle}
            onContactEmailToggle={handleContactEmailToggle}
            onContactPhoneToggle={handleContactPhoneToggle}
          />
        ) : preferencesLoadState === 'error' ? (
          <div className="subscribe-section" role="alert">
            <p className="subscribe-hint">{preferencesLoadError}</p>
            <button
              type="button"
              className="subscribe-submit"
              onClick={() => void loadPreferences()}
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="subscribe-section" role="status">
            <p className="subscribe-hint">
              Loading subscription preferences...
            </p>
          </div>
        )
      )}
    </div>
  );
};
