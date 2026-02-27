import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export const RegisterForm = () => {
  const { register, error, isLoading, setPendingEmail, clearError } = useAuth();
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
      const response = await register(
        email,
        password,
        passwordConfirm,
        firstName.trim(),
        lastName.trim(),
        organization.trim() || undefined,
      );
      const pending = response.email || email;
      setPendingEmail(pending);
      navigate(`/verify-pending?email=${encodeURIComponent(pending)}`, { replace: true });
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

      <div className="auth-form-row">
        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-first-name">
            First Name
          </label>
          <input
            id="register-first-name"
            type="text"
            className={`auth-form-input ${localErrors.firstName ? 'has-error' : ''}`}
            value={firstName}
            onChange={(e) => {
              setFirstName(e.target.value);
              setLocalErrors((prev) => ({ ...prev, firstName: '' }));
              clearError();
            }}
            placeholder="First name"
            required
            autoComplete="given-name"
          />
          {localErrors.firstName && (
            <span className="auth-form-error">{localErrors.firstName}</span>
          )}
        </div>

        <div className="auth-form-group">
          <label className="auth-form-label" htmlFor="register-last-name">
            Last Name
          </label>
          <input
            id="register-last-name"
            type="text"
            className={`auth-form-input ${localErrors.lastName ? 'has-error' : ''}`}
            value={lastName}
            onChange={(e) => {
              setLastName(e.target.value);
              setLocalErrors((prev) => ({ ...prev, lastName: '' }));
              clearError();
            }}
            placeholder="Last name"
            required
            autoComplete="family-name"
          />
          {localErrors.lastName && (
            <span className="auth-form-error">{localErrors.lastName}</span>
          )}
        </div>
      </div>

      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="register-organization">
          Organization <span style={{ fontWeight: 400, color: '#9ca3af' }}>(optional)</span>
        </label>
        <input
          id="register-organization"
          type="text"
          className="auth-form-input"
          value={organization}
          onChange={(e) => {
            setOrganization(e.target.value);
            clearError();
          }}
          placeholder="Company or organization"
          autoComplete="organization"
        />
      </div>

      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="register-email">
          Email
        </label>
        <input
          id="register-email"
          type="email"
          className="auth-form-input"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            clearError();
          }}
          placeholder="your@email.com"
          required
          autoComplete="email"
        />
      </div>

      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="register-password">
          Password
        </label>
        <input
          id="register-password"
          type="password"
          className={`auth-form-input ${localErrors.password ? 'has-error' : ''}`}
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setLocalErrors((prev) => ({ ...prev, password: '' }));
            clearError();
          }}
          placeholder="At least 8 characters"
          required
          autoComplete="new-password"
          minLength={8}
        />
        {localErrors.password && (
          <span className="auth-form-error">{localErrors.password}</span>
        )}
      </div>

      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="register-password-confirm">
          Confirm Password
        </label>
        <input
          id="register-password-confirm"
          type="password"
          className={`auth-form-input ${localErrors.passwordConfirm ? 'has-error' : ''}`}
          value={passwordConfirm}
          onChange={(e) => {
            setPasswordConfirm(e.target.value);
            setLocalErrors((prev) => ({ ...prev, passwordConfirm: '' }));
            clearError();
          }}
          placeholder="Re-enter your password"
          required
          autoComplete="new-password"
        />
        {localErrors.passwordConfirm && (
          <span className="auth-form-error">{localErrors.passwordConfirm}</span>
        )}
      </div>

      <button
        type="submit"
        className="auth-form-submit"
        disabled={isLoading || !firstName || !lastName || !email || !password || !passwordConfirm}
      >
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Creating account...
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
