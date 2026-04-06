import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { getProfile, updateProfileFields } from '../../../services/auth';
import { getAuthErrorMessage } from '../context/shared';
import { CompleteProfileForm } from './CompleteProfileForm';
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
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationType, setOrganizationType] = useState<'personal' | 'organization'>('personal');
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
        setMiddleName(profile.middle_name ?? '');
        setLastName(profile.last_name ?? '');
        const org = profile.organization ?? '';
        const isPersonal = !org || org.toLowerCase() === 'personal';
        setOrganizationType(isPersonal ? 'personal' : 'organization');
        setOrganization(isPersonal ? '' : org);
      } catch (err: unknown) {
        setError(getAuthErrorMessage(err));
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
      const orgValue = organizationType === 'personal' ? 'Personal' : organization.trim();
      await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: orgValue,
      });
      clearProfileCompletionRequirement();
      navigate('/account', { replace: true });
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
            onOrganizationTypeChange={(value) => {
              setOrganizationType(value);
              setOrganization('');
            }}
            setOrganization={setOrganization}
            clearError={() => setError(null)}
            onSubmit={handleSubmit}
          />
        )}
      </div>
    </div>
  );
};
