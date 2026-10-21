import {useEffect, useState} from 'react';
import {useSearchParams} from 'react-router';
import {useAuth} from '@/features/auth';
import type {ProfileResponse} from '@/features/auth/api/types';
import {CodeStep} from './steps/CodeStep';
import {EmailStep} from './steps/EmailStep';
import {ManageStep} from './steps/ManageStep';
import {ProfileStep} from './steps/ProfileStep';
import {LoadStatePanel} from './subscription/LoadStatePanel';
import type {SubscribeWizardStep} from './subscription/types';
import {useSubscribeSignIn} from './subscription/useSubscribeSignIn';
import {useSubscriberProfile} from './subscription/useSubscriberProfile';
import {useSubscriptionPreferences} from './subscription/useSubscriptionPreferences';

/** The lead line, and on the manage step what these settings do not cover. */
const SubscribeIntro = ({step}: {step: SubscribeWizardStep}) => (
  <div className="subscribe-info">
    <p className="itg-lead subscribe-lead">
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
);

/** The profile form once the profile has loaded, else its loading / failed state. */
const ProfilePanel = ({profileForm}: {profileForm: ReturnType<typeof useSubscriberProfile>}) =>
  profileForm.loadState === 'ready' ? (
    <ProfileStep
      {...profileForm.fields}
      saving={profileForm.saving}
      onFirstNameChange={profileForm.onFirstNameChange}
      onMiddleNameChange={profileForm.onMiddleNameChange}
      onLastNameChange={profileForm.onLastNameChange}
      onOrganizationTypeChange={profileForm.onOrganizationTypeChange}
      onOrganizationChange={profileForm.onOrganizationChange}
      onTitleChange={profileForm.onTitleChange}
      onSubmit={profileForm.handleSubmit}
    />
  ) : (
    <LoadStatePanel
      failed={profileForm.loadState === 'error'}
      errorMessage={profileForm.loadError}
      loadingMessage="Loading your profile..."
      onRetry={() => void profileForm.load()}
    />
  );

interface ManagePanelProps {
  preferences: ReturnType<typeof useSubscriptionPreferences>;
  profile: ProfileResponse | null;
  message: string | null;
}

/** The subscription toggles once the preferences have loaded, else their loading / failed state. */
const ManagePanel = ({preferences, profile, message}: ManagePanelProps) =>
  preferences.loadState === 'ready' && profile ? (
    <ManageStep
      profile={profile}
      contactEmails={preferences.contactEmails}
      contactPhones={preferences.contactPhones}
      savingId={preferences.savingId}
      message={message}
      onPrimaryEmailToggle={preferences.togglePrimaryEmail}
      onContactEmailToggle={preferences.toggleContactEmail}
      onContactPhoneToggle={preferences.toggleContactPhone}
    />
  ) : (
    <LoadStatePanel
      failed={preferences.loadState === 'error'}
      errorMessage={preferences.loadError}
      loadingMessage="Loading subscription preferences..."
      onRetry={() => void preferences.load()}
    />
  );

/**
 * Newsletter and text-message subscriptions: sign in (email or phone code), complete the profile when
 * needed, then manage each address's opt-ins. The steps' state lives in `subscription/` hooks.
 */
export const SubscribePage = () => {
  const [searchParams] = useSearchParams();
  const {isAuthenticated, isLoading, clearError} = useAuth();
  const shouldStartInProfile = searchParams.get('step') === 'profile';

  const [step, setStep] = useState<SubscribeWizardStep>(() => {
    if (!isAuthenticated) {
      return 'email';
    }
    return shouldStartInProfile ? 'profile' : 'manage';
  });
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [preferenceMessage, setPreferenceMessage] = useState<string | null>(null);

  const clearPageError = () => {
    setError(null);
    setPreferenceMessage(null);
    clearError();
  };

  const signIn = useSubscribeSignIn({setStep, setError, clearPageError});
  const profileForm = useSubscriberProfile({
    step,
    isAuthenticated,
    initiallyLoading: isAuthenticated && shouldStartInProfile,
    setProfile,
    setStep,
    setError,
    clearPageError,
  });
  const preferences = useSubscriptionPreferences({
    step,
    isAuthenticated,
    initiallyLoading: isAuthenticated && !shouldStartInProfile,
    setProfile,
    setMessage: setPreferenceMessage,
    setError,
    clearPageError,
  });

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

  return (
    <div className="subscribe-page">
      <h1 className="itg-page-title subscribe-title">Subscriptions</h1>

      <SubscribeIntro step={step} />

      {error && <div className="subscribe-alert error" role="alert">{error}</div>}

      {step === 'email' && (
        <EmailStep
          email={signIn.email}
          authLoading={isLoading}
          onEmailChange={(value) => {
            signIn.setEmail(value);
            clearPageError();
          }}
          onSubmit={signIn.handleEmailSubmit}
        />
      )}

      {step === 'code' && (
        <CodeStep
          email={signIn.email}
          code={signIn.code}
          authLoading={isLoading}
          onCodeChange={(value) => {
            signIn.setCode(value);
            clearPageError();
          }}
          onSubmit={signIn.handleCodeSubmit}
          onBack={signIn.handleCodeBack}
          onResend={signIn.handleResendCode}
        />
      )}

      {step === 'profile' && <ProfilePanel profileForm={profileForm} />}

      {step === 'manage' && (
        <ManagePanel preferences={preferences} profile={profile} message={preferenceMessage} />
      )}
    </div>
  );
};
