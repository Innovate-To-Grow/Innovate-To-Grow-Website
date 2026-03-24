import {useState, useEffect, useCallback, type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import {useAuth} from '../../components/Auth';
import {updateProfileFields} from '../../services/auth';
import {
  fetchRegistrationOptions,
  createRegistration,
  type EventRegistrationOptions,
  type Registration,
} from '../../services/api/events';
import './EventRegistrationPage.css';

type Step = 'loading' | 'email' | 'code' | 'profile' | 'form' | 'done';

export const EventRegistrationPage = () => {
  const {isAuthenticated, requiresProfileCompletion, requestEmailAuthCode, verifyEmailAuthCode, clearProfileCompletionRequirement} = useAuth();

  const [step, setStep] = useState<Step>('loading');
  const [options, setOptions] = useState<EventRegistrationOptions | null>(null);
  const [registration, setRegistration] = useState<Registration | null>(null);
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

  // Form state
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const loadOptions = useCallback(async () => {
    try {
      const data = await fetchRegistrationOptions();
      setOptions(data);

      if (data.registration) {
        setRegistration(data.registration);
        setStep('done');
      } else if (isAuthenticated) {
        setStep('form');
      } else {
        setStep('email');
      }
    } catch (err: unknown) {
      const msg = getErrorMessage(err);
      const axiosErr = err as {response?: {status?: number}};

      // If token is invalid/expired, treat as unauthenticated and show email step
      if (axiosErr.response?.status === 401) {
        setStep('email');
        return;
      }

      if (msg.toLowerCase().includes('no live event')) {
        setError('No event is currently accepting registrations.');
      } else {
        setError(msg);
      }
      setStep('loading'); // stay on loading with error
    }
  }, [isAuthenticated]);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  // When auth state changes (user logs in), decide next step
  useEffect(() => {
    if (isAuthenticated && (step === 'email' || step === 'code')) {
      // New user without name — show profile step first
      if (requiresProfileCompletion) {
        setStep('profile');
      } else {
        setStep('loading');
        loadOptions();
      }
    }
  }, [isAuthenticated, requiresProfileCompletion, step, loadOptions]);

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
      await verifyEmailAuthCode(email.trim(), code.trim());
      // The useEffect above handles routing:
      // - New user (requiresProfileCompletion) → profile step
      // - Existing user → reload options → form step
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
      });
      clearProfileCompletionRequirement();
      setStep('loading');
      loadOptions();
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleRegistrationSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!options || !selectedTicketId) return;

    setSubmitting(true);
    setError(null);
    try {
      const result = await createRegistration({
        event_slug: options.slug,
        ticket_id: selectedTicketId,
        answers: Object.entries(answers)
          .filter(([, v]) => v.trim())
          .map(([qId, answer]) => ({question_id: qId, answer})),
      });
      setRegistration(result);
      setStep('done');
    } catch (err: unknown) {
      // Check for 409 conflict (already registered)
      const axiosErr = err as {response?: {status?: number; data?: {registration?: Registration; detail?: string}}};
      if (axiosErr.response?.status === 409 && axiosErr.response.data?.registration) {
        setRegistration(axiosErr.response.data.registration);
        setStep('done');
      } else {
        setError(getErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Loading / error state
  if (step === 'loading') {
    if (error) {
      return (
        <div className="event-reg-page">
          <h1 className="event-reg-title">Event Registration</h1>
          <div className="event-reg-alert error">{error}</div>
        </div>
      );
    }
    return (
      <div className="event-reg-page">
        <div className="event-reg-loading">Loading event details...</div>
      </div>
    );
  }

  // Done / confirmation
  if (step === 'done' && registration) {
    return (
      <div className="event-reg-page">
        <div className="event-reg-done">
          <h2>You're Registered!</h2>
          <p className="event-reg-done-subtitle">
            Your ticket for <strong>{registration.event.name}</strong> is confirmed.
          </p>

          <img
            src={registration.barcode_image}
            alt="Ticket barcode"
            className="event-reg-barcode"
          />

          <div className="event-reg-ticket-code">{registration.ticket_code}</div>

          <div className="event-reg-done-details">
            <p><strong>Ticket:</strong> {registration.ticket.name}</p>
            <p><strong>Date:</strong> {formatDate(registration.event.date)}</p>
            <p><strong>Location:</strong> {registration.event.location}</p>
          </div>

          {registration.ticket_email_sent_at ? (
            <div className="event-reg-done-email-notice">
              A confirmation email with your ticket has been sent to {registration.attendee_email}.
            </div>
          ) : registration.ticket_email_error ? (
            <div className="event-reg-done-email-error">
              We couldn't send the confirmation email. You can resend it from your account page.
            </div>
          ) : null}

          <Link to="/account" className="event-reg-link">View My Account</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="event-reg-page">
      <h1 className="event-reg-title">Event Registration</h1>

      {/* Event info banner */}
      {options && (
        <div className="event-reg-info">
          <h2>{options.name}</h2>
          <p><strong>Date:</strong> {formatDate(options.date)}</p>
          <p><strong>Location:</strong> {options.location}</p>
          {options.description && <p style={{marginTop: '0.5rem'}}>{options.description}</p>}
        </div>
      )}

      {error && <div className="event-reg-alert error">{error}</div>}

      {/* Email auth step */}
      {step === 'email' && (
        <div className="event-reg-auth">
          <p className="event-reg-auth-hint">
            Enter your email to continue. Your email will be used to create an account.
            If an account with this email already exists, you'll be signed in.
          </p>
          <form onSubmit={handleEmailSubmit}>
            <div className="event-reg-form-group">
              <label className="event-reg-label" htmlFor="reg-email">Email</label>
              <input
                id="reg-email"
                type="email"
                className="event-reg-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoFocus
                disabled={authLoading}
              />
            </div>
            <button type="submit" className="event-reg-submit" disabled={authLoading || !email.trim()}>
              {authLoading ? <><span className="event-reg-spinner" /> Sending code...</> : 'Continue with Email'}
            </button>
          </form>
        </div>
      )}

      {/* Code verification step */}
      {step === 'code' && (
        <div className="event-reg-auth">
          <p className="event-reg-auth-hint">
            A verification code has been sent to <strong>{email}</strong>.
            {authFlow === 'register'
              ? ' A new account will be created for you.'
              : ' You will be signed in to your existing account.'}
          </p>
          <form onSubmit={handleCodeSubmit}>
            <div className="event-reg-form-group">
              <label className="event-reg-label" htmlFor="reg-code">Verification Code</label>
              <input
                id="reg-code"
                type="text"
                className="event-reg-input"
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
            <button type="submit" className="event-reg-submit" disabled={authLoading || !code.trim()}>
              {authLoading ? <><span className="event-reg-spinner" /> Verifying...</> : 'Verify Code'}
            </button>
          </form>
          <button
            type="button"
            style={{marginTop: '0.75rem', background: 'none', border: 'none', color: '#003366', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'underline'}}
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

      {/* Profile completion step (new accounts) */}
      {step === 'profile' && (
        <div className="event-reg-auth">
          <p className="event-reg-auth-hint">
            Please provide your name and organization to continue with registration.
          </p>
          <form onSubmit={handleProfileSubmit}>
            <div className="event-reg-form-row">
              <div className="event-reg-form-group">
                <label className="event-reg-label" htmlFor="reg-first-name">
                  First Name <span className="required-mark">*</span>
                </label>
                <input
                  id="reg-first-name"
                  type="text"
                  className="event-reg-input"
                  value={firstName}
                  onChange={(e) => { setFirstName(e.target.value); setError(null); }}
                  placeholder="First name"
                  autoComplete="given-name"
                  required
                  autoFocus
                  disabled={saving}
                />
              </div>
              <div className="event-reg-form-group">
                <label className="event-reg-label" htmlFor="reg-last-name">
                  Last Name <span className="event-reg-optional">(optional)</span>
                </label>
                <input
                  id="reg-last-name"
                  type="text"
                  className="event-reg-input"
                  value={lastName}
                  onChange={(e) => { setLastName(e.target.value); setError(null); }}
                  placeholder="Last name"
                  autoComplete="family-name"
                  disabled={saving}
                />
              </div>
            </div>
            <div className="event-reg-form-group">
              <label className="event-reg-label" htmlFor="reg-org">
                Organization <span className="event-reg-optional">(optional)</span>
              </label>
              <input
                id="reg-org"
                type="text"
                className="event-reg-input"
                value={organization}
                onChange={(e) => { setOrganization(e.target.value); setError(null); }}
                placeholder="Company or organization"
                autoComplete="organization"
                disabled={saving}
              />
            </div>
            <button type="submit" className="event-reg-submit" disabled={saving || !firstName.trim()}>
              {saving ? <><span className="event-reg-spinner" /> Saving...</> : 'Continue'}
            </button>
          </form>
        </div>
      )}

      {/* Registration form step */}
      {step === 'form' && options && (
        <form onSubmit={handleRegistrationSubmit}>
          {/* Ticket selection */}
          <div className="event-reg-form-group">
            <label className="event-reg-label">Select a Ticket <span className="required-mark">*</span></label>
            <div className="event-reg-tickets">
              {options.tickets.map((ticket) => {
                const isSoldOut = ticket.is_sold_out;
                return (
                  <label
                    key={ticket.id}
                    className={`event-reg-ticket-option${selectedTicketId === ticket.id ? ' selected' : ''}${isSoldOut ? ' sold-out' : ''}`}
                  >
                    <input
                      type="radio"
                      name="ticket"
                      value={ticket.id}
                      checked={selectedTicketId === ticket.id}
                      onChange={() => setSelectedTicketId(ticket.id)}
                      disabled={isSoldOut}
                    />
                    <span className="event-reg-ticket-name">
                      {ticket.name}
                      {ticket.price !== '0.00' && (
                        <span className="event-reg-ticket-price"> — ${ticket.price}</span>
                      )}
                    </span>
                    {ticket.remaining_quantity !== null && (
                      <span className="event-reg-ticket-meta">
                        {isSoldOut ? 'Sold out' : `${ticket.remaining_quantity} left`}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          </div>

          {/* Questions */}
          {options.questions
            .sort((a, b) => a.order - b.order)
            .map((q) => (
              <div key={q.id} className="event-reg-form-group">
                <label className="event-reg-label" htmlFor={`q-${q.id}`}>
                  {q.text}
                  {q.is_required && <span className="required-mark">*</span>}
                </label>
                <textarea
                  id={`q-${q.id}`}
                  className="event-reg-input event-reg-textarea"
                  value={answers[q.id] || ''}
                  onChange={(e) => setAnswers((prev) => ({...prev, [q.id]: e.target.value}))}
                  required={q.is_required}
                />
              </div>
            ))}

          <button
            type="submit"
            className="event-reg-submit"
            disabled={submitting || !selectedTicketId}
          >
            {submitting ? <><span className="event-reg-spinner" /> Registering...</> : 'Register'}
          </button>
        </form>
      )}
    </div>
  );
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', {year: 'numeric', month: 'long', day: 'numeric'});
}

function getErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.message === 'string') return data.message;
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value)) return value[0] as string;
        if (typeof value === 'string') return value;
      }
    }
  }
  return 'An unexpected error occurred. Please try again.';
}
