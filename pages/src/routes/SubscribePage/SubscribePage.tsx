import {useEffect, useState, type FormEvent} from 'react';
import {useSearchParams} from 'react-router-dom';
import {useAuth} from '@/features/auth';
import {
  getAccessToken,
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

function hasStoredAccessToken() {
  try {
    return Boolean(getAccessToken());
  } catch {
    return false;
  }
}

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
  const [profileLoading, setProfileLoading] = useState(() => isAuthenticated && shouldStartInProfile);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [contactEmails, setContactEmails] = useState<ContactEmail[]>([]);
  const [contactPhones, setContactPhones] = useState<ContactPhone[]>([]);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferenceSavingId, setPreferenceSavingId] = useState<string | null>(null);
  const [preferenceMessage, setPreferenceMessage] = useState<string | null>(null);

  const applyProfileToForm = (nextProfile: ProfileResponse) => {
    setFirstName(nextProfile.first_name ?? '');
    setMiddleName(nextProfile.middle_name ?? '');
    setLastName(nextProfile.last_name ?? '');

    const org = nextProfile.organization ?? '';
    const normalized = org.trim().toLowerCase();
    const isIndividual = ['individual', 'personal'].includes(normalized);
    setOrganizationType(isIndividual ? 'individual' : 'organization');
    setOrganization(isIndividual ? '' : org);
    setTitle(nextProfile.title ?? '');
  };

  // When auth state changes after verification, advance out of the email/code
  // steps, but do not override an in-progress profile or manage screen.
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    if (step === 'email' || step === 'code') {
      if (shouldStartInProfile) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- external sync: isAuthenticated flips asynchronously via the i2g-auth-state-change event (not a local handler), so this transition out of email/code must stay in the effect; showing the loader synchronously before the profile fetch is load-bearing for the auth-timing gap.
        setProfileLoading(true);
      }
      setStep(shouldStartInProfile ? 'profile' : 'manage');
    }
  }, [isAuthenticated, shouldStartInProfile, step]);

  // Fetch profile data for the direct profile-link flow so existing account
  // details are preserved before completion.
  useEffect(() => {
    const hasSession = isAuthenticated || hasStoredAccessToken();
    if (!hasSession || step !== 'profile') {
      return;
    }

    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- external sync: ensures the loader shows before the async getProfile() resolves; this guards the hasStoredAccessToken auth-timing path where the effect (re)runs on a profile-link load and must not flash the form before data arrives.
    setProfileLoading(true);

    getProfile()
      .then((nextProfile) => {
        if (cancelled) {
          return;
        }
        setProfile(nextProfile);
        applyProfileToForm(nextProfile);
      })
      .catch(() => {
        if (!cancelled) {
          setError('Failed to load your profile.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setProfileLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [step, isAuthenticated]);

  useEffect(() => {
    const hasSession = isAuthenticated || hasStoredAccessToken();
    if (!hasSession || step !== 'manage') {
      return;
    }

    let cancelled = false;

    Promise.all([getProfile(), getContactEmails(), getContactPhones()])
      .then(([nextProfile, nextContactEmails, nextContactPhones]) => {
        if (cancelled) {
          return;
        }
        setProfile(nextProfile);
        setContactEmails(nextContactEmails);
        setContactPhones(nextContactPhones);
      })
      .catch(() => {
        if (!cancelled) {
          setError('Failed to load subscription preferences.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPreferencesLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [step, isAuthenticated]);

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
        setProfileLoading(true);
        setStep('profile');
      } else {
        setPreferencesLoading(true);
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
      setPreferencesLoading(true);
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
        profileLoading ? (
          <div className="subscribe-section" role="status">
            Loading your profile...
          </div>
        ) : (
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
        )
      )}

      {step === 'manage' && (
        <ManageStep
          profile={profile}
          contactEmails={contactEmails}
          contactPhones={contactPhones}
          loading={preferencesLoading}
          savingId={preferenceSavingId}
          message={preferenceMessage}
          onPrimaryEmailToggle={handlePrimaryEmailToggle}
          onContactEmailToggle={handleContactEmailToggle}
          onContactPhoneToggle={handleContactPhoneToggle}
        />
      )}
    </div>
  );
};
