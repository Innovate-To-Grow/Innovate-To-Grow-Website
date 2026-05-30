import {useEffect, useState, type FormEvent} from 'react';

import {CodeInput} from '../../../components/Auth';

interface CodeStepProps {
  email: string;
  code: string;
  authLoading: boolean;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onBack: () => void;
  onResend: () => Promise<void>;
}

const RESEND_COOLDOWN = 30;

export const CodeStep = ({
  email,
  code,
  authLoading,
  onCodeChange,
  onSubmit,
  onBack,
  onResend,
}: CodeStepProps) => {
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((prev) => prev - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const handleResend = async () => {
    setResending(true);
    try {
      await onResend();
      setCooldown(RESEND_COOLDOWN);
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="subscribe-section">
      <p className="subscribe-hint">
        A verification code has been sent to <strong>{email}</strong>.
      </p>
      <form onSubmit={onSubmit}>
        <div className="subscribe-form-group">
          <label className="subscribe-label" htmlFor="subscribe-code">
            Verification Code
          </label>
          <CodeInput
            id="subscribe-code"
            value={code}
            onChange={onCodeChange}
            disabled={authLoading}
            autoFocus
            required
          />
        </div>
        <button type="submit" className="subscribe-submit" disabled={authLoading || code.length !== 6}>
          {authLoading ? <><span className="subscribe-spinner" /> Verifying...</> : 'Verify Code'}
        </button>
      </form>
      <div className="subscribe-code-actions">
        <button type="button" className="subscribe-back-link" onClick={onBack}>
          Use a different email
        </button>
        <button
          type="button"
          className="subscribe-back-link"
          onClick={handleResend}
          disabled={cooldown > 0 || resending}
        >
          {resending ? 'Sending...' : cooldown > 0 ? `Resend code (${cooldown}s)` : 'Resend code'}
        </button>
      </div>
    </div>
  );
};
