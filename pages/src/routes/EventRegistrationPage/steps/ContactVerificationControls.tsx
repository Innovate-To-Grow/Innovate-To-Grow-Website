import type {ReactNode} from 'react';
import {VERIFICATION_CODE_PLACEHOLDER} from '@/features/auth';

interface ContactVerificationControlsProps {
  children: ReactNode;
  contactLabel: string;
  enabled: boolean;
  hasValue: boolean;
  invalid: boolean;
  submitting: boolean;
  code: string;
  codeSent: boolean;
  sending: boolean;
  verified: boolean;
  verifying: boolean;
  onCodeChange: (value: string) => void;
  onSendCode: () => void;
  onVerifyCode: () => void;
}

export const ContactVerificationControls = ({
  children, contactLabel, enabled, hasValue, invalid, submitting,
  code, codeSent, sending, verified, verifying, onCodeChange, onSendCode, onVerifyCode,
}: ContactVerificationControlsProps) => (
  <>
    <div className="event-reg-phone-row">
      {children}
      {enabled && !verified ? (
        <button
          type="button"
          className="event-reg-phone-action"
          aria-label={`${codeSent ? 'Resend' : 'Send'} ${contactLabel.toLowerCase()} code`}
          disabled={!hasValue || invalid || submitting || sending || verifying}
          onClick={onSendCode}
        >
          {sending ? 'Sending...' : codeSent ? 'Resend' : 'Send Code'}
        </button>
      ) : null}
      {verified ? <span className="event-reg-phone-verified">Verified</span> : null}
    </div>
    {enabled && codeSent && !verified ? (
      <div className="event-reg-phone-code-row">
        <input
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          className="event-reg-input"
          value={code}
          onChange={(event) => onCodeChange(event.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder={VERIFICATION_CODE_PLACEHOLDER}
          aria-label={`${contactLabel} verification code`}
          disabled={submitting || sending || verifying}
        />
        <button
          type="button"
          className="event-reg-phone-action"
          aria-label={`Verify ${contactLabel.toLowerCase()}`}
          disabled={code.length !== 6 || submitting || sending || verifying}
          onClick={onVerifyCode}
        >
          {verifying ? 'Verifying...' : 'Verify'}
        </button>
      </div>
    ) : null}
  </>
);
