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

type ControlProps = Omit<ContactVerificationControlsProps, 'children' | 'enabled'>;

/** "Send Code" (or "Resend") next to the contact field. */
const SendCodeButton = ({contactLabel, hasValue, invalid, submitting, codeSent, sending, verifying, onSendCode}: ControlProps) => (
  <button
    type="button"
    className="itg-btn itg-btn-outline event-reg-phone-action"
    aria-label={`${codeSent ? 'Resend' : 'Send'} ${contactLabel.toLowerCase()} code`}
    disabled={!hasValue || invalid || submitting || sending || verifying}
    onClick={onSendCode}
  >
    {sending ? 'Sending...' : codeSent ? 'Resend' : 'Send Code'}
  </button>
);

/** The code field and its Verify button, once a code was sent. */
const CodeEntryRow = ({contactLabel, submitting, code, sending, verifying, onCodeChange, onVerifyCode}: ControlProps) => (
  <div className="event-reg-phone-code-row">
    <input
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={6}
      className="itg-input event-reg-input"
      value={code}
      onChange={(event) => onCodeChange(event.target.value.replace(/\D/g, '').slice(0, 6))}
      placeholder={VERIFICATION_CODE_PLACEHOLDER}
      aria-label={`${contactLabel} verification code`}
      disabled={submitting || sending || verifying}
    />
    <button
      type="button"
      className="itg-btn itg-btn-outline event-reg-phone-action"
      aria-label={`Verify ${contactLabel.toLowerCase()}`}
      disabled={code.length !== 6 || submitting || sending || verifying}
      onClick={onVerifyCode}
    >
      {verifying ? 'Verifying...' : 'Verify'}
    </button>
  </div>
);

/** A contact field with its send-code / enter-code / verified controls (when the event verifies it). */
export const ContactVerificationControls = ({children, enabled, ...controls}: ContactVerificationControlsProps) => (
  <>
    <div className="event-reg-phone-row">
      {children}
      {enabled && !controls.verified ? <SendCodeButton {...controls} /> : null}
      {controls.verified ? <span className="itg-tag itg-tag-saved event-reg-phone-verified">Verified</span> : null}
    </div>
    {enabled && controls.codeSent && !controls.verified ? <CodeEntryRow {...controls} /> : null}
  </>
);
