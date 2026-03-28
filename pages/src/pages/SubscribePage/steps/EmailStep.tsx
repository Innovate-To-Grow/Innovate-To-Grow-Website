import type {FormEvent} from 'react';

interface EmailStepProps {
  email: string;
  authLoading: boolean;
  onEmailChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export const EmailStep = ({email, authLoading, onEmailChange, onSubmit}: EmailStepProps) => (
  <div className="subscribe-section">
    <p className="subscribe-hint">
      Enter your email to continue. If an account with this email already exists, you'll be signed in.
    </p>
    <form onSubmit={onSubmit}>
      <div className="subscribe-form-group">
        <label className="subscribe-label" htmlFor="subscribe-email">
          Email
        </label>
        <input
          id="subscribe-email"
          type="email"
          className="subscribe-input"
          value={email}
          onChange={(event) => onEmailChange(event.target.value)}
          placeholder="you@example.com"
          required
          autoFocus
          disabled={authLoading}
        />
      </div>
      <button type="submit" className="subscribe-submit" disabled={authLoading || !email.trim()}>
        {authLoading ? <><span className="subscribe-spinner" /> Sending code...</> : 'Continue with Email'}
      </button>
    </form>
  </div>
);
