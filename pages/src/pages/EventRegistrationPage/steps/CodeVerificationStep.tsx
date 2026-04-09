import type {FormEvent} from 'react';

import {CodeInput} from '../../../components/Auth';

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
        <label className="event-reg-label" htmlFor="reg-code">
          Verification Code
        </label>
        <CodeInput
          id="reg-code"
          value={code}
          onChange={onCodeChange}
          disabled={authLoading}
          autoFocus
          required
        />
      </div>
      <button type="submit" className="event-reg-submit" disabled={authLoading || code.length !== 6}>
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
