import type {FormEvent} from 'react';

interface EmailAuthStepProps {
  email: string;
  authLoading: boolean;
  onEmailChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export const EmailAuthStep = ({email, authLoading, onEmailChange, onSubmit}: EmailAuthStepProps) => (
  <div className="event-reg-auth">
    <p className="event-reg-auth-hint">
      Enter your email to continue. Your email will be used to create an account. If an account with this email already
      exists, you'll be signed in.
    </p>
    <form onSubmit={onSubmit}>
      <div className="event-reg-form-group">
        <label className="event-reg-label" htmlFor="reg-email">Email</label>
        <input
          id="reg-email"
          type="email"
          className="event-reg-input"
          value={email}
          onChange={(event) => onEmailChange(event.target.value)}
          placeholder="you@example.com"
          required
          autoFocus
          disabled={authLoading}
        />
      </div>
      <button type="submit" className="event-reg-submit" disabled={authLoading || !email.trim()}>
        {authLoading ? <><span className="event-reg-spinner" /> Sending code...</> : 'Continue with Email'}
      </button>
    </form>
  </div>
);
