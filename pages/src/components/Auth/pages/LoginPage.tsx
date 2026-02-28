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
        <div className="auth-page-header">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
          <h1 className="auth-page-title">Welcome to I2G</h1>
          <p className="auth-page-subtitle">Sign in to your account</p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
};
