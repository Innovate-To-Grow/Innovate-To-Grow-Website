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
      Enter your email or phone to continue. We'll send a verification code and create your account if you don't have
      one yet.
    </p>
    <form onSubmit={onSubmit}>
      <div className="event-reg-form-group">
        <label className="event-reg-label" htmlFor="reg-email">Email or Phone</label>
        <input
          id="reg-email"
          type="text"
          className="event-reg-input"
          value={email}
          onChange={(event) => onEmailChange(event.target.value)}
          placeholder="you@example.com or (201) 555-0123"
          autoComplete="username"
          required
          autoFocus
          disabled={authLoading}
        />
      </div>
      <button type="submit" className="event-reg-submit" disabled={authLoading || !email.trim()}>
        {authLoading ? <><span className="event-reg-spinner" /> Sending code...</> : 'Continue'}
      </button>
    </form>
  </div>
);
