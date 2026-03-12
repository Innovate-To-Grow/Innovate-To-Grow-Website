import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { getProfile, updateProfileFields } from '../../../services/auth';
import '../Auth.css';

export const CompleteProfilePage = () => {
  const {
    isAuthenticated,
    requiresProfileCompletion,
    clearProfileCompletionRequirement,
  } = useAuth();
  const navigate = useNavigate();

  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !requiresProfileCompletion) {
      return;
    }

    const loadProfile = async () => {
      try {
        const profile = await getProfile();
        setFirstName(profile.first_name ?? '');
        setLastName(profile.last_name ?? '');
        setOrganization(profile.organization ?? '');
      } catch (err: unknown) {
        setError(getErrorMessage(err));
      } finally {
        setIsBootstrapping(false);
      }
    };

    loadProfile();
  }, [isAuthenticated, requiresProfileCompletion]);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!requiresProfileCompletion) {
    return <Navigate to="/account" replace />;
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!firstName.trim()) {
      setError('First name is required.');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await updateProfileFields({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        organization: organization.trim(),
      });
      clearProfileCompletionRequirement();
      navigate('/account', { replace: true });
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-page-card wide">
        <div className="auth-page-header">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
          <h1 className="auth-page-title">Complete Your Profile</h1>
          <p className="auth-page-subtitle">Add your name and organization before continuing to your account.</p>
        </div>

        {error && (
          <div className="auth-alert-wrapper">
            <div className="auth-alert error" role="alert">
              <i className="fa fa-exclamation-circle auth-alert-icon" aria-hidden />
              <span>{error}</span>
            </div>
          </div>
        )}

        {isBootstrapping ? (
          <div className="auth-alert-wrapper">
            <div className="auth-alert info" role="status">
              <i className="fa fa-info-circle auth-alert-icon" aria-hidden />
              <span>Loading your profile...</span>
            </div>
          </div>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="auth-form-row">
              <div className="auth-form-group">
                <label className="auth-form-label" htmlFor="complete-profile-first-name">
                  First Name
                </label>
                <input
                  id="complete-profile-first-name"
                  type="text"
                  className="auth-form-input"
                  value={firstName}
                  onChange={(event) => {
                    setFirstName(event.target.value);
                    setError(null);
                  }}
                  placeholder="First name"
                  autoComplete="given-name"
                  required
                />
              </div>

              <div className="auth-form-group">
                <label className="auth-form-label" htmlFor="complete-profile-last-name">
                  Last Name <span style={{ fontWeight: 400, color: '#9ca3af' }}>(optional)</span>
                </label>
                <input
                  id="complete-profile-last-name"
                  type="text"
                  className="auth-form-input"
                  value={lastName}
                  onChange={(event) => {
                    setLastName(event.target.value);
                    setError(null);
                  }}
                  placeholder="Last name"
                  autoComplete="family-name"
                />
              </div>
            </div>

            <div className="auth-form-group">
              <label className="auth-form-label" htmlFor="complete-profile-organization">
                Organization <span style={{ fontWeight: 400, color: '#9ca3af' }}>(optional)</span>
              </label>
              <input
                id="complete-profile-organization"
                type="text"
                className="auth-form-input"
                value={organization}
                onChange={(event) => {
                  setOrganization(event.target.value);
                  setError(null);
                }}
                placeholder="Company or organization"
                autoComplete="organization"
              />
            </div>

            <button
              type="submit"
              className="auth-form-submit"
              disabled={isSaving || !firstName.trim()}
            >
              {isSaving ? (
                <>
                  <span className="auth-spinner" />
                  Saving profile...
                </>
              ) : (
                'Continue to Account'
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

function getErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const response = (err as { response?: { data?: Record<string, unknown> } }).response;
    if (response?.data) {
      const messages: string[] = [];
      for (const value of Object.values(response.data)) {
        if (Array.isArray(value)) {
          for (const item of value) {
            if (typeof item === 'string') {
              messages.push(item);
            }
          }
        } else if (typeof value === 'string') {
          messages.push(value);
        }
      }
      if (messages.length > 0) {
        return messages.join(' ');
      }
    }
  }
  return 'Failed to complete your profile. Please try again.';
}
