import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export const LoginForm = () => {
  const { login, error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await login(email, password);
      navigate('/account', { replace: true });
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
        <label className="auth-form-label" htmlFor="login-email">
          Email
        </label>
        <input
          id="login-email"
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
        <label className="auth-form-label" htmlFor="login-password">
          Password
        </label>
        <input
          id="login-password"
          type="password"
          className="auth-form-input"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            clearError();
          }}
          placeholder="Enter your password"
          required
          autoComplete="current-password"
        />
      </div>

      <button
        type="submit"
        className="auth-form-submit"
        disabled={isLoading || !email || !password}
      >
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Signing in...
          </>
        ) : (
          'Sign In'
        )}
      </button>

      <div className="auth-switch">
        Don't have an account?{' '}
        <button
          type="button"
          className="auth-switch-link"
          onClick={() => navigate('/register')}
        >
          Create one
        </button>
      </div>
    </form>
  );
};
