import {useEffect, useState, type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import {useAuth} from '../../components/Auth';
import {RegisterFields} from '../../components/Auth/forms/RegisterFields';
import '../../components/Auth/Auth.css';
import {updateProfileFields} from '../../services/auth';
import {DoneStep} from './steps/DoneStep';
import {getSubscribeErrorMessage} from './steps/helpers';
import './SubscribePage.css';

type OrganizationType = 'personal' | 'organization';

export const SubscribePage = () => {
  const {user, isAuthenticated, register, error: authError, isLoading, clearError} = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationType, setOrganizationType] = useState<OrganizationType>('personal');
  const [organization, setOrganization] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});
  const [pageError, setPageError] = useState<string | null>(null);
  const [subscribeLoading, setSubscribeLoading] = useState(false);
  const [doneEmail, setDoneEmail] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      setEmail(user?.email ?? '');
      setPageError(null);
      setLocalErrors({});
      return;
    }

    setEmail('');
    setDoneEmail('');
  }, [isAuthenticated, user?.email]);

  const validateRegistration = () => {
    const errors: Record<string, string> = {};

    if (!firstName.trim()) {
      errors.firstName = 'First name is required';
    }

    if (!lastName.trim()) {
      errors.lastName = 'Last name is required';
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Please enter a valid email address';
    }

    if (organizationType === 'organization' && !organization.trim()) {
      errors.organization = 'Organization name is required';
    }

    if (password.length < 8) {
      errors.password = 'Password must be at least 8 characters';
    }

    if (password !== passwordConfirm) {
      errors.passwordConfirm = 'Passwords do not match';
    }

    setLocalErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleRegisterSubmit = async (event: FormEvent) => {
    event.preventDefault();
    clearError();
    setPageError(null);

    if (!validateRegistration()) {
      return;
    }

    const normalizedEmail = email.trim().toLowerCase();
    const orgValue = organizationType === 'personal' ? 'Personal' : organization.trim();

    try {
      await register(
        normalizedEmail,
        password,
        passwordConfirm,
        firstName.trim(),
        lastName.trim(),
        orgValue,
      );

      navigate(
        `/verify-email?flow=register&email=${encodeURIComponent(normalizedEmail)}&returnTo=${encodeURIComponent('/subscribe')}`,
        {replace: true},
      );
    } catch {
      // Error is handled by the auth context.
    }
  };

  const handleSubscribeSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      setPageError('We could not find an email address for your account.');
      return;
    }

    setSubscribeLoading(true);
    setPageError(null);
    try {
      const profile = await updateProfileFields({email_subscribe: true});
      const subscribedEmail = profile.email || email.trim();
      setDoneEmail(subscribedEmail);
      setEmail(subscribedEmail);
    } catch (err: unknown) {
      setPageError(getSubscribeErrorMessage(err));
    } finally {
      setSubscribeLoading(false);
    }
  };

  if (doneEmail) {
    return <DoneStep email={doneEmail} />;
  }

  const error = pageError ?? authError;
  const registerDisabled =
    isLoading ||
    !firstName.trim() ||
    !lastName.trim() ||
    !email.trim() ||
    !password ||
    !passwordConfirm ||
    (organizationType === 'organization' && !organization.trim());

  return (
    <div className="subscribe-page">
      <h1 className="subscribe-title">Subscribe</h1>

      <div className="subscribe-info">
        <h2>Stay Updated</h2>
        <p>
          {isAuthenticated
            ? 'You are signed in. Confirm your account email below to receive updates and announcements.'
            : 'Create your account with the standard registration flow, then subscribe your email to receive updates and announcements.'}
        </p>
      </div>

      {error && <div className="subscribe-alert error">{error}</div>}

      {isAuthenticated ? (
        <div className="subscribe-section">
          <p className="subscribe-hint">This page uses your signed-in account email for subscription preferences.</p>
          <form onSubmit={handleSubscribeSubmit}>
            <div className="subscribe-form-group">
              <label className="subscribe-label" htmlFor="subscribe-account-email">
                Email
              </label>
              <input
                id="subscribe-account-email"
                type="email"
                className="subscribe-input"
                value={email}
                readOnly
                disabled
              />
            </div>
            <button type="submit" className="subscribe-submit" disabled={subscribeLoading || !email.trim()}>
              {subscribeLoading ? <><span className="subscribe-spinner" /> Subscribing...</> : 'Subscribe'}
            </button>
          </form>
        </div>
      ) : (
        <div className="subscribe-section">
          <p className="subscribe-hint">Register with your email and password first. We will ask you to verify your email before continuing.</p>
          <form className="auth-form" onSubmit={handleRegisterSubmit}>
            <RegisterFields
              firstName={firstName}
              lastName={lastName}
              organizationType={organizationType}
              organization={organization}
              email={email}
              password={password}
              passwordConfirm={passwordConfirm}
              localErrors={localErrors}
              onFirstNameChange={(value) => {
                setFirstName(value);
                setLocalErrors((prev) => ({...prev, firstName: ''}));
                clearError();
                setPageError(null);
              }}
              onLastNameChange={(value) => {
                setLastName(value);
                setLocalErrors((prev) => ({...prev, lastName: ''}));
                clearError();
                setPageError(null);
              }}
              onOrganizationTypeChange={(value) => {
                setOrganizationType(value);
                setOrganization('');
                setLocalErrors((prev) => ({...prev, organization: ''}));
                clearError();
                setPageError(null);
              }}
              onOrganizationChange={(value) => {
                setOrganization(value);
                setLocalErrors((prev) => ({...prev, organization: ''}));
                clearError();
                setPageError(null);
              }}
              onEmailChange={(value) => {
                setEmail(value);
                setLocalErrors((prev) => ({...prev, email: ''}));
                clearError();
                setPageError(null);
              }}
              onPasswordChange={(value) => {
                setPassword(value);
                setLocalErrors((prev) => ({...prev, password: ''}));
                clearError();
                setPageError(null);
              }}
              onPasswordConfirmChange={(value) => {
                setPasswordConfirm(value);
                setLocalErrors((prev) => ({...prev, passwordConfirm: ''}));
                clearError();
                setPageError(null);
              }}
            />

            <button type="submit" className="subscribe-submit" disabled={registerDisabled}>
              {isLoading ? <><span className="subscribe-spinner" /> Sending verification code...</> : 'Create Account and Continue'}
            </button>
          </form>

          <div className="auth-switch">
            <p>Already have an account?</p>
            <button type="button" className="auth-switch-link" onClick={() => navigate('/login')}>
              Sign In
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
