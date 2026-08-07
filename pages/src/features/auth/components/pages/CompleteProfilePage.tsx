import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { useAuth } from '../AuthContext';
import {
  getProfile,
  getStoredSession,
  isCurrentSession,
  updateProfileFields,
} from '@/features/auth/api';
import { getSafeInternalRedirectPath } from '@/features/auth/api/redirects';
import { getAuthErrorMessage } from '../context/shared';
import { CompleteProfileForm } from './CompleteProfileForm';

export const CompleteProfilePage = () => {
  const {
    user,
    isAuthenticated,
    requiresProfileCompletion,
    clearProfileCompletionRequirement,
  } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = getSafeInternalRedirectPath(searchParams.get('returnTo'));

  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationType, setOrganizationType] = useState<'individual' | 'organization'>('organization');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !requiresProfileCompletion) {
      return;
    }
    const session = getStoredSession();
    if (!session) return;
    const guard = {
      generation: session.generation,
    };
    let active = true;

    const loadProfile = async () => {
      await Promise.resolve();
      if (!active || !isCurrentSession(guard)) return;
      setIsBootstrapping(true);
      setError(null);
      setFirstName('');
      setMiddleName('');
      setLastName('');
      setOrganizationType('organization');
      setOrganization('');
      setTitle('');
      try {
        const profile = await getProfile();
        if (!active || !isCurrentSession(guard)) return;
        setFirstName(profile.first_name ?? '');
        setMiddleName(profile.middle_name ?? '');
        setLastName(profile.last_name ?? '');
        const org = profile.organization ?? '';
        const normalized = org.trim().toLowerCase();
        const isIndividual = ['individual', 'personal'].includes(normalized);
        setOrganizationType(isIndividual ? 'individual' : 'organization');
        setOrganization(isIndividual ? '' : org);
        setTitle(profile.title ?? '');
      } catch (err: unknown) {
        if (!active || !isCurrentSession(guard)) return;
        setError(getAuthErrorMessage(err));
      } finally {
        if (active && isCurrentSession(guard)) {
          setIsBootstrapping(false);
        }
      }
    };

    void loadProfile();
    return () => {
      active = false;
    };
  }, [
    isAuthenticated,
    requiresProfileCompletion,
    user?.member_uuid,
  ]);

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

    if (!lastName.trim()) {
      setError('Last name is required.');
      return;
    }

    if (organizationType === 'organization' && !organization.trim()) {
      setError('Organization name is required.');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const session = getStoredSession();
      if (!session) return;
      const guard = {
        generation: session.generation,
      };
      const orgValue = organizationType === 'individual' ? 'Individual' : organization.trim();
      const titleValue = organizationType === 'organization' ? title.trim() : '';
      await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: orgValue,
        title: titleValue,
      });
      if (!clearProfileCompletionRequirement(guard)) return;
      navigate(returnTo ?? '/account', { replace: true });
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
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
          <CompleteProfileForm
            firstName={firstName}
            middleName={middleName}
            lastName={lastName}
            organizationType={organizationType}
            organization={organization}
            isSaving={isSaving}
            setFirstName={setFirstName}
            setMiddleName={setMiddleName}
            setLastName={setLastName}
            title={title}
            onOrganizationTypeChange={(value) => {
              setOrganizationType(value);
              setOrganization('');
              setTitle('');
            }}
            setOrganization={setOrganization}
            setTitle={setTitle}
            clearError={() => setError(null)}
            onSubmit={handleSubmit}
          />
        )}
      </div>
    </div>
  );
};
