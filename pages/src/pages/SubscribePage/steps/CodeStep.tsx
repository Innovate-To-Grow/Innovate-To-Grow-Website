import type {FormEvent} from 'react';

interface CodeStepProps {
  email: string;
  code: string;
  authLoading: boolean;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onBack: () => void;
}

export const CodeStep = ({
  email,
  code,
  authLoading,
  onCodeChange,
  onSubmit,
  onBack,
}: CodeStepProps) => (
  <div className="subscribe-section">
    <p className="subscribe-hint">
      A verification code has been sent to <strong>{email}</strong>.
    </p>
    <form onSubmit={onSubmit}>
      <div className="subscribe-form-group">
        <label className="subscribe-label" htmlFor="subscribe-code">
          Verification Code
        </label>
        <input
          id="subscribe-code"
          type="text"
          className="subscribe-input"
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
      <button type="submit" className="subscribe-submit" disabled={authLoading || !code.trim()}>
        {authLoading ? <><span className="subscribe-spinner" /> Verifying...</> : 'Verify Code'}
      </button>
    </form>
    <button type="button" className="subscribe-back-link" onClick={onBack}>
      Use a different email
    </button>
  </div>
);
