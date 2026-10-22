import '../auth.css';
import {Icon} from '@/components/Icon/Icon';
import { Navigate, useSearchParams } from 'react-router';
import { getSafeInternalRedirectPath } from '@/features/auth/api/redirects';
import { CompleteProfileForm } from './CompleteProfileForm';
import { useCompleteProfile } from './useCompleteProfile';

export const CompleteProfilePage = () => {
  const [searchParams] = useSearchParams();
  const returnTo = getSafeInternalRedirectPath(searchParams.get('returnTo'));
  const { isAuthenticated, requiresProfileCompletion, form, isBootstrapping, isSaving, error, setError, handleSubmit } =
    useCompleteProfile(returnTo);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!requiresProfileCompletion) {
    return <Navigate to="/account" replace />;
  }

  return (
    <div className="auth-page auth-page--wide">
      <header className="auth-page-header">
        <h1 className="itg-page-title auth-page-title">Complete Your Profile</h1>
        <p className="itg-page-meta auth-page-subtitle">Add your name and organization before continuing to your account.</p>
      </header>
      <div className="itg-panel auth-page-card">

        {error && (
          <div className="auth-alert-wrapper">
            <div className="auth-alert error" role="alert">
              <Icon name="exclamation-circle" className="auth-alert-icon" />
              <span>{error}</span>
            </div>
          </div>
        )}

        {isBootstrapping ? (
          <div className="auth-alert-wrapper">
            <div className="auth-alert info" role="status">
              <Icon name="info-circle" className="auth-alert-icon" />
              <span>Loading your profile...</span>
            </div>
          </div>
        ) : (
          <CompleteProfileForm
            firstName={form.firstName}
            middleName={form.middleName}
            lastName={form.lastName}
            organizationType={form.organizationType}
            organization={form.organization}
            isSaving={isSaving}
            setFirstName={form.setFirstName}
            setMiddleName={form.setMiddleName}
            setLastName={form.setLastName}
            title={form.title}
            onOrganizationTypeChange={(value) => {
              form.setOrganizationType(value);
              form.setOrganization('');
              form.setTitle('');
            }}
            setOrganization={form.setOrganization}
            setTitle={form.setTitle}
            clearError={() => setError(null)}
            onSubmit={handleSubmit}
          />
        )}
      </div>
    </div>
  );
};
