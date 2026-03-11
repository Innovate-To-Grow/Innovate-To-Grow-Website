import { useState, useEffect, type FormEvent } from 'react';
import {
  getContactEmails,
  createContactEmail,
  updateContactEmail,
  deleteContactEmail,
  requestContactEmailVerification,
  verifyContactEmailCode,
  updateProfileFields,
  type ProfileResponse,
  type ContactEmail,
} from '../../../services/auth';
import { CodeInput } from '../forms/CodeInput';
import '../Auth.css';

interface EmailCenterProps {
  profile: ProfileResponse;
  onProfileUpdate: (updated: ProfileResponse) => void;
}

function getErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as { response?: { data?: Record<string, unknown> } };
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
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

export const EmailCenter = ({ profile, onProfileUpdate }: EmailCenterProps) => {
  const [contactEmails, setContactEmails] = useState<ContactEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Subscribe toggle state
  const [subscribeSaving, setSubscribeSaving] = useState(false);

  // Add form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [addEmail, setAddEmail] = useState('');
  const [addType, setAddType] = useState<'secondary' | 'other'>('secondary');
  const [addSubscribe, setAddSubscribe] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Verify state (which contact email is being verified)
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);

  useEffect(() => {
    const fetchEmails = async () => {
      try {
        const data = await getContactEmails();
        setContactEmails(data);
      } catch (err) {
        console.error('[EmailCenter] Failed to load contact emails:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchEmails();
  }, []);

  const clearMessages = () => {
    setError(null);
    setSuccessMessage(null);
  };

  const handlePrimarySubscribeToggle = async () => {
    const newValue = !profile.email_subscribe;
    setSubscribeSaving(true);
    clearMessages();
    try {
      const updated = await updateProfileFields({ email_subscribe: newValue });
      onProfileUpdate(updated);
      setSuccessMessage(`Primary email ${newValue ? 'subscribed' : 'unsubscribed'}.`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubscribeSaving(false);
    }
  };

  const handleContactSubscribeToggle = async (contact: ContactEmail) => {
    clearMessages();
    try {
      const updated = await updateContactEmail(contact.id, { subscribe: !contact.subscribe });
      setContactEmails((prev) => prev.map((c) => (c.id === contact.id ? updated : c)));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleContactTypeChange = async (contact: ContactEmail, newType: 'secondary' | 'other') => {
    clearMessages();
    try {
      const updated = await updateContactEmail(contact.id, { email_type: newType });
      setContactEmails((prev) => prev.map((c) => (c.id === contact.id ? updated : c)));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleAddSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setAddLoading(true);
    setAddError(null);
    clearMessages();
    try {
      const created = await createContactEmail({
        email_address: addEmail.trim(),
        email_type: addType,
        subscribe: addSubscribe,
      });
      setContactEmails((prev) => [created, ...prev]);
      setAddEmail('');
      setAddType('secondary');
      setAddSubscribe(false);
      setShowAddForm(false);
      setVerifyingId(created.id);
      setVerifyCode('');
      setSuccessMessage('Email added. Please enter the verification code sent to your email.');
    } catch (err) {
      setAddError(getErrorMessage(err));
    } finally {
      setAddLoading(false);
    }
  };

  const handleVerifySubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!verifyingId || verifyCode.length !== 6) return;
    setVerifyLoading(true);
    setVerifyError(null);
    clearMessages();
    try {
      const updated = await verifyContactEmailCode(verifyingId, verifyCode);
      setContactEmails((prev) => prev.map((c) => (c.id === verifyingId ? updated : c)));
      setVerifyingId(null);
      setVerifyCode('');
      setSuccessMessage('Email verified successfully.');
    } catch (err) {
      setVerifyError(getErrorMessage(err));
    } finally {
      setVerifyLoading(false);
    }
  };

  const handleResend = async (contactId: string) => {
    setResendLoading(true);
    setVerifyError(null);
    try {
      await requestContactEmailVerification(contactId);
      setSuccessMessage('Verification code resent.');
    } catch (err) {
      setVerifyError(getErrorMessage(err));
    } finally {
      setResendLoading(false);
    }
  };

  const handleDelete = async (contactId: string) => {
    if (!window.confirm('Are you sure you want to remove this email?')) return;
    clearMessages();
    try {
      await deleteContactEmail(contactId);
      setContactEmails((prev) => prev.filter((c) => c.id !== contactId));
      if (verifyingId === contactId) {
        setVerifyingId(null);
        setVerifyCode('');
      }
      setSuccessMessage('Email removed.');
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div className="account-section">
      <h2 className="account-section-title">Subscriptions</h2>

      {successMessage && (
        <div className="auth-alert success" style={{ marginBottom: '1rem' }}>
          <i className="fa fa-check-circle auth-alert-icon" />
          <span>{successMessage}</span>
        </div>
      )}

      {error && (
        <div className="auth-alert error" style={{ marginBottom: '1rem' }}>
          <i className="fa fa-exclamation-circle auth-alert-icon" />
          <span>{error}</span>
        </div>
      )}

      {/* Primary Email */}
      <div className="email-center-card">
        <div className="email-center-row">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 600, color: '#1f2937', wordBreak: 'break-all' }}>{profile.email}</span>
              <span className="email-center-badge primary">Primary</span>
            </div>
          </div>
          <label className="email-center-toggle" aria-label="Subscribe primary email">
            <input
              type="checkbox"
              checked={profile.email_subscribe}
              onChange={handlePrimarySubscribeToggle}
              disabled={subscribeSaving}
            />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Subscribe</span>
          </label>
        </div>
      </div>

      {/* Connected Emails */}
      {loading ? (
        <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>Loading connected emails...</p>
      ) : (
        contactEmails.map((contact) => (
          <div key={contact.id} className="email-center-card">
            <div className="email-center-row">
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 500, color: '#1f2937', wordBreak: 'break-all' }}>
                    {contact.email_address}
                  </span>
                  <span className={`email-center-badge ${contact.verified ? 'verified' : 'unverified'}`}>
                    {contact.verified ? 'Verified' : 'Unverified'}
                  </span>
                </div>
                <div className="email-center-actions">
                  <select
                    className="email-center-type-select"
                    value={contact.email_type}
                    onChange={(e) =>
                      handleContactTypeChange(contact, e.target.value as 'secondary' | 'other')
                    }
                  >
                    <option value="secondary">Secondary</option>
                    <option value="other">Other</option>
                  </select>
                  <label className="email-center-toggle" aria-label="Subscribe this email">
                    <input
                      type="checkbox"
                      checked={contact.subscribe}
                      onChange={() => handleContactSubscribeToggle(contact)}
                    />
                    <span className="email-center-toggle-slider" />
                    <span className="email-center-toggle-label">Subscribe</span>
                  </label>
                  {!contact.verified && (
                    <button
                      type="button"
                      className="email-center-btn verify"
                      onClick={() => {
                        setVerifyingId(verifyingId === contact.id ? null : contact.id);
                        setVerifyCode('');
                        setVerifyError(null);
                      }}
                    >
                      Verify
                    </button>
                  )}
                  <button
                    type="button"
                    className="email-center-btn delete"
                    onClick={() => handleDelete(contact.id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>

            {/* Inline verification */}
            {verifyingId === contact.id && !contact.verified && (
              <div className="email-center-verify-inline">
                <form onSubmit={handleVerifySubmit} className="email-center-verify-form">
                  <CodeInput value={verifyCode} onChange={setVerifyCode} disabled={verifyLoading} />
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button
                      type="submit"
                      className="auth-form-submit"
                      disabled={verifyLoading || verifyCode.length !== 6}
                      style={{ flex: 1, marginTop: 0, fontSize: '0.875rem', padding: '0.625rem 1rem' }}
                    >
                      {verifyLoading ? (
                        <>
                          <span className="auth-spinner" />
                          Verifying...
                        </>
                      ) : (
                        'Submit Code'
                      )}
                    </button>
                    <button
                      type="button"
                      className="email-center-btn verify"
                      disabled={resendLoading}
                      onClick={() => handleResend(contact.id)}
                      style={{ fontSize: '0.8125rem' }}
                    >
                      {resendLoading ? 'Sending...' : 'Resend Code'}
                    </button>
                    <button
                      type="button"
                      className="email-center-btn delete"
                      onClick={() => {
                        setVerifyingId(null);
                        setVerifyCode('');
                        setVerifyError(null);
                      }}
                      style={{ fontSize: '0.8125rem' }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
                {verifyError && (
                  <div className="auth-alert error" style={{ marginTop: '0.5rem' }}>
                    <i className="fa fa-exclamation-circle auth-alert-icon" />
                    <span>{verifyError}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))
      )}

      {/* Add Email Button / Form */}
      {showAddForm ? (
        <div className="email-center-add-form">
          <h3 className="account-subsection-title">Add Connected Email</h3>
          {addError && (
            <div className="auth-alert error" style={{ marginBottom: '0.75rem' }}>
              <i className="fa fa-exclamation-circle auth-alert-icon" />
              <span>{addError}</span>
            </div>
          )}
          <form onSubmit={handleAddSubmit} className="email-center-add-fields">
            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="add-contact-email">
                Email Address
              </label>
              <input
                id="add-contact-email"
                type="email"
                className="auth-form-input"
                value={addEmail}
                onChange={(e) => setAddEmail(e.target.value)}
                placeholder="email@example.com"
                required
                disabled={addLoading}
              />
            </div>
            <div className="account-form-row">
              <div className="auth-form-group">
                <label className="auth-form-label" htmlFor="add-contact-type">
                  Type
                </label>
                <select
                  id="add-contact-type"
                  className="auth-form-input auth-form-select"
                  value={addType}
                  onChange={(e) => setAddType(e.target.value as 'secondary' | 'other')}
                  disabled={addLoading}
                >
                  <option value="secondary">Secondary</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="auth-form-group" style={{ justifyContent: 'center' }}>
                <label className="email-center-toggle" style={{ marginTop: '1.5rem' }}>
                  <input
                    type="checkbox"
                    checked={addSubscribe}
                    onChange={(e) => setAddSubscribe(e.target.checked)}
                    disabled={addLoading}
                  />
                  <span className="email-center-toggle-slider" />
                  <span className="email-center-toggle-label">Subscribe</span>
                </label>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                type="submit"
                className="auth-form-submit"
                disabled={addLoading || !addEmail.trim()}
                style={{ flex: 1 }}
              >
                {addLoading ? (
                  <>
                    <span className="auth-spinner" />
                    Adding...
                  </>
                ) : (
                  'Add & Send Verification'
                )}
              </button>
              <button
                type="button"
                className="auth-form-submit"
                onClick={() => {
                  setShowAddForm(false);
                  setAddError(null);
                }}
                style={{ flex: 1, background: '#fff', color: '#003366', border: '1px solid #003366' }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      ) : (
        <button
          type="button"
          className="auth-form-submit"
          onClick={() => {
            setShowAddForm(true);
            clearMessages();
          }}
          style={{ marginTop: '0.75rem' }}
        >
          Add Email
        </button>
      )}
    </div>
  );
};
