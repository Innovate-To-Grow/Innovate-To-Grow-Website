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
      <div className="auth-page-card">
        <h1 className="auth-page-title">Create Account</h1>
        <RegisterForm />
      </div>
    </div>
  );
};
