import { useState, type FormEvent } from 'react';
import { useAuth } from './AuthContext';

export const RegisterForm = () => {
  const { register, error, isLoading, openModal, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

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
      await register(email, password, passwordConfirm);
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
        disabled={isLoading || !email || !password || !passwordConfirm}
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
        Already have an account?{' '}
        <button
          type="button"
          className="auth-switch-link"
          onClick={() => openModal('login')}
        >
          Sign in
        </button>
      </div>
    </form>
  );
};

