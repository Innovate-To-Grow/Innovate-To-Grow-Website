import type {FormEvent} from 'react';

import {CodeInput} from '@/features/auth';

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
  <div className="itg-panel event-reg-auth">
    <p className="event-reg-auth-hint">
      A verification code has been sent to <strong>{email}</strong>.
    </p>
    <form onSubmit={onSubmit}>
      <div className="event-reg-form-group">
        <label className="itg-label event-reg-label" htmlFor="reg-code">
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
      <button type="submit" className="itg-btn itg-btn-primary event-reg-submit" disabled={authLoading || code.length !== 6}>
        {authLoading ? <><span className="event-reg-spinner" /> Verifying...</> : 'Verify Code'}
      </button>
    </form>
    <button type="button" className="itg-btn itg-btn-text event-reg-text-button" onClick={onBack}>
      Use a different email or phone
    </button>
  </div>
);
