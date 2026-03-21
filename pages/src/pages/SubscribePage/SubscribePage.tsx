import {useState, useEffect, type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import {useAuth} from '../../components/Auth';
import {updateProfileFields} from '../../services/auth';
import './SubscribePage.css';

type Step = 'email' | 'code' | 'profile' | 'done';

export const SubscribePage = () => {
  const {isAuthenticated, requestEmailAuthCode, verifyEmailAuthCode, clearProfileCompletionRequirement} = useAuth();

  const [step, setStep] = useState<Step>('email');
  const [error, setError] = useState<string | null>(null);

  // Auth state
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authFlow, setAuthFlow] = useState<string | null>(null);

  // Profile state
  const [firstName, setFirstName] = useState('');
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
      setError(getErrorMessage(err));
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
      setError(getErrorMessage(err));
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
        last_name: lastName.trim(),
        organization: organization.trim(),
        email_subscribe: true,
      });
      clearProfileCompletionRequirement();
      setStep('done');
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  // Done / confirmation
  if (step === 'done') {
    return (
      <div className="subscribe-page">
        <div className="subscribe-done">
          <h2>You're Subscribed!</h2>
          <p className="subscribe-done-subtitle">
            You'll receive updates and announcements at <strong>{email}</strong>.
          </p>
          <div className="subscribe-done-notice">
            Your account has been created and you are now subscribed to our communications.
          </div>
          <Link to="/account" className="subscribe-link">View My Account</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="subscribe-page">
      <h1 className="subscribe-title">Subscribe</h1>

      <div className="subscribe-info">
        <h2>Stay Updated</h2>
        <p>Subscribe to receive the latest updates and announcements. Your email will be used to create an account so you can manage your preferences.</p>
      </div>

      {error && <div className="subscribe-alert error">{error}</div>}

      {/* Step 1: Email */}
      {step === 'email' && (
        <div className="subscribe-section">
          <p className="subscribe-hint">
            Enter your email to continue. If an account with this email already exists, you'll be signed in.
          </p>
          <form onSubmit={handleEmailSubmit}>
            <div className="subscribe-form-group">
              <label className="subscribe-label" htmlFor="subscribe-email">Email</label>
              <input
                id="subscribe-email"
                type="email"
                className="subscribe-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoFocus
                disabled={authLoading}
              />
            </div>
            <button type="submit" className="subscribe-submit" disabled={authLoading || !email.trim()}>
              {authLoading ? <><span className="subscribe-spinner" /> Sending code...</> : 'Continue with Email'}
            </button>
          </form>
        </div>
      )}

      {/* Step 2: Code verification */}
      {step === 'code' && (
        <div className="subscribe-section">
          <p className="subscribe-hint">
            A verification code has been sent to <strong>{email}</strong>.
            {authFlow === 'register'
              ? ' A new account will be created for you.'
              : ' You will be signed in to your existing account.'}
          </p>
          <form onSubmit={handleCodeSubmit}>
            <div className="subscribe-form-group">
              <label className="subscribe-label" htmlFor="subscribe-code">Verification Code</label>
              <input
                id="subscribe-code"
                type="text"
                className="subscribe-input"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Enter 6-digit code"
                required
                autoFocus
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={6}
                disabled={authLoading}
              />
            </div>
            <button type="submit" className="subscribe-submit" disabled={authLoading || !code.trim()}>
              {authLoading ? <><span className="subscribe-spinner" /> Verifying...</> : 'Verify Code'}
            </button>
          </form>
          <button
            type="button"
            className="subscribe-back-link"
            onClick={() => {
              setCode('');
              setError(null);
              setStep('email');
            }}
          >
            Use a different email
          </button>
        </div>
      )}

      {/* Step 3: Profile completion (new accounts) */}
      {step === 'profile' && (
        <div className="subscribe-section">
          <p className="subscribe-hint">
            Complete your profile to finish subscribing.
          </p>
          <form onSubmit={handleProfileSubmit}>
            <div className="subscribe-form-row">
              <div className="subscribe-form-group">
                <label className="subscribe-label" htmlFor="subscribe-first-name">
                  First Name <span className="subscribe-required">*</span>
                </label>
                <input
                  id="subscribe-first-name"
                  type="text"
                  className="subscribe-input"
                  value={firstName}
                  onChange={(e) => { setFirstName(e.target.value); setError(null); }}
                  placeholder="First name"
                  autoComplete="given-name"
                  required
                  autoFocus
                  disabled={saving}
                />
              </div>
              <div className="subscribe-form-group">
                <label className="subscribe-label" htmlFor="subscribe-last-name">
                  Last Name <span className="subscribe-optional">(optional)</span>
                </label>
                <input
                  id="subscribe-last-name"
                  type="text"
                  className="subscribe-input"
                  value={lastName}
                  onChange={(e) => { setLastName(e.target.value); setError(null); }}
                  placeholder="Last name"
                  autoComplete="family-name"
                  disabled={saving}
                />
              </div>
            </div>
            <div className="subscribe-form-group">
              <label className="subscribe-label" htmlFor="subscribe-org">
                Organization <span className="subscribe-optional">(optional)</span>
              </label>
              <input
                id="subscribe-org"
                type="text"
                className="subscribe-input"
                value={organization}
                onChange={(e) => { setOrganization(e.target.value); setError(null); }}
                placeholder="Company or organization"
                autoComplete="organization"
                disabled={saving}
              />
            </div>
            <button type="submit" className="subscribe-submit" disabled={saving || !firstName.trim()}>
              {saving ? <><span className="subscribe-spinner" /> Subscribing...</> : 'Subscribe'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};

function getErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.message === 'string') return data.message;
      const messages: string[] = [];
      for (const value of Object.values(data)) {
        if (Array.isArray(value)) {
          for (const item of value) {
            if (typeof item === 'string') messages.push(item);
          }
        } else if (typeof value === 'string') {
          messages.push(value);
        }
      }
      if (messages.length > 0) return messages.join(' ');
    }
  }
  return 'An unexpected error occurred. Please try again.';
}
