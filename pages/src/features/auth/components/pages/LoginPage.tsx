import { Navigate, useSearchParams } from 'react-router-dom';
import { buildCompleteProfilePath, getSafeInternalRedirectPath } from '@/features/auth/api/redirects';
import { useAuth } from '../AuthContext';
import { LoginForm } from '../forms/LoginForm';

export const LoginPage = () => {
  const { isAuthenticated, requiresProfileCompletion } = useAuth();
  const [searchParams] = useSearchParams();
  const returnTo = getSafeInternalRedirectPath(searchParams.get('returnTo'));

  if (isAuthenticated) {
    // An already-signed-in visitor who hits a returnTo login link still gets sent back;
    // profile completion takes precedence but carries returnTo through the detour.
    if (requiresProfileCompletion) {
      return <Navigate to={buildCompleteProfilePath(returnTo)} replace />;
    }
    return <Navigate to={returnTo ?? '/account'} replace />;
  }

  return (
    <div className="auth-page">
      <div className="auth-page-card">
        <div className="auth-page-header">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
          <h1 className="auth-page-title">Welcome to I2G</h1>
          <p className="auth-page-subtitle">Enter your email to sign in or create your account</p>
        </div>
        <LoginForm returnTo={returnTo} />
      </div>
    </div>
  );
};
