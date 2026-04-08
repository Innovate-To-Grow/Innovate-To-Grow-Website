import type {FormEvent} from 'react';

interface CodeVerificationStepProps {
  email: string;
  code: string;
  authLoading: boolean;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onBack: () => void;
}

export const CodeVerificationStep = ({
  email,
  code,
  authLoading,
  onCodeChange,
  onSubmit,
  onBack,
}: CodeVerificationStepProps) => (
  <div className="event-reg-auth">
    <p className="event-reg-auth-hint">
      A verification code has been sent to <strong>{email}</strong>.
    </p>
    <form onSubmit={onSubmit}>
      <div className="event-reg-form-group">
        <label className="event-reg-label" htmlFor="reg-code">Verification Code</label>
        <input
          id="reg-code"
          type="text"
          className="event-reg-input"
          value={code}
          onChange={(event) => onCodeChange(event.target.value)}
          placeholder="Enter 6-digit code"
          required
          autoFocus
          autoComplete="one-time-code"
          inputMode="numeric"
          maxLength={6}
          disabled={authLoading}
        />
      </div>
      <button type="submit" className="event-reg-submit" disabled={authLoading || !code.trim()}>
        {authLoading ? <><span className="event-reg-spinner" /> Verifying...</> : 'Verify Code'}
      </button>
    </form>
    <button
      type="button"
      style={{marginTop: '0.75rem', background: 'none', border: 'none', color: '#003366', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'underline'}}
      onClick={onBack}
    >
      Use a different email
    </button>
  </div>
);
