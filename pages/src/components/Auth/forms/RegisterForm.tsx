import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { RegisterFields } from './RegisterFields';

export const RegisterForm = () => {
  const { register, error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (!firstName.trim()) {
      errors.firstName = 'First name is required';
    }

    if (!lastName.trim()) {
      errors.lastName = 'Last name is required';
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errors.email = 'Please enter a valid email address';
    }

    if (password.length < 8) {
      errors.password = 'Password must be at least 8 characters';
    }

    if (password !== passwordConfirm) {
      errors.passwordConfirm = 'Passwords do not match';
    }

    setLocalErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      await register(
        email,
        password,
        passwordConfirm,
        firstName.trim(),
        lastName.trim(),
        organization.trim() || undefined,
      );
      navigate(`/verify-email?flow=register&email=${encodeURIComponent(email.trim().toLowerCase())}`, { replace: true });
    } catch {
      // Error is handled by context
    }
  };

  return (
    <form className="auth-form" onSubmit={handleSubmit}>
      {error && (
        <div className="auth-alert error">
          <i className="fa fa-exclamation-circle auth-alert-icon" />
          <span>{error}</span>
        </div>
      )}

      <RegisterFields
        firstName={firstName}
        lastName={lastName}
        organization={organization}
        email={email}
        password={password}
        passwordConfirm={passwordConfirm}
        localErrors={localErrors}
        onFirstNameChange={(value) => {
          setFirstName(value);
          setLocalErrors((prev) => ({ ...prev, firstName: '' }));
          clearError();
        }}
        onLastNameChange={(value) => {
          setLastName(value);
          setLocalErrors((prev) => ({ ...prev, lastName: '' }));
          clearError();
        }}
        onOrganizationChange={(value) => {
          setOrganization(value);
          clearError();
        }}
        onEmailChange={(value) => {
          setEmail(value);
          setLocalErrors((prev) => ({ ...prev, email: '' }));
          clearError();
        }}
        onPasswordChange={(value) => {
          setPassword(value);
          setLocalErrors((prev) => ({ ...prev, password: '' }));
          clearError();
        }}
        onPasswordConfirmChange={(value) => {
          setPasswordConfirm(value);
          setLocalErrors((prev) => ({ ...prev, passwordConfirm: '' }));
          clearError();
        }}
      />

      <button
        type="submit"
        className="auth-form-submit"
        disabled={isLoading || !firstName || !lastName || !email || !password || !passwordConfirm}
      >
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Sending verification code...
          </>
        ) : (
          'Create Account'
        )}
      </button>

      <div className="auth-switch">
        <p>Already have an account?</p>
        <button
          type="button"
          className="auth-switch-link"
          onClick={() => navigate('/login')}
        >
          Sign In
        </button>
      </div>
    </form>
  );
};
