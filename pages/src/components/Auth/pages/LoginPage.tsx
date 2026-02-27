import { Navigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { LoginForm } from '../forms/LoginForm';
import '../Auth.css';

export const LoginPage = () => {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/account" replace />;
  }

  return (
    <div className="auth-page">
      <div className="auth-page-card">
        <h1 className="auth-page-title">Sign In</h1>
        <LoginForm />
      </div>
    </div>
  );
};
