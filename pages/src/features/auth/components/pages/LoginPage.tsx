import { Navigate, useSearchParams } from 'react-router';
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
      <header className="auth-page-header">
        <h1 className="itg-page-title auth-page-title">Welcome to I2G</h1>
        <p className="itg-page-meta auth-page-subtitle">Enter your email or phone number to sign in or create your account</p>
      </header>
      <div className="itg-panel auth-page-card">
        <LoginForm returnTo={returnTo} />
      </div>
    </div>
  );
};
