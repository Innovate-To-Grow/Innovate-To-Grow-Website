import { Navigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { RegisterForm } from '../forms/RegisterForm';
import '../Auth.css';

export const RegisterPage = () => {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/account" replace />;
  }

  return (
    <div className="auth-page">
      <div className="auth-page-card wide">
        <div className="auth-page-header">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="auth-page-logo" />
          <h1 className="auth-page-title">Create Account</h1>
          <p className="auth-page-subtitle">Join the Innovate to Grow community</p>
        </div>
        <RegisterForm />
      </div>
    </div>
  );
};
