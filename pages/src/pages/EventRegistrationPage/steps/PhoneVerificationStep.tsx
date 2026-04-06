import type {FormEvent} from 'react';

interface PhoneVerificationStepProps {
  phone: string;
  phoneCode: string;
  verifying: boolean;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onResend: () => void;
}

export const PhoneVerificationStep = ({
  phone,
  phoneCode,
  verifying,
  onCodeChange,
  onSubmit,
  onResend,
}: PhoneVerificationStepProps) => (
  <form onSubmit={onSubmit}>
    <p className="event-reg-step-description">
      A verification code has been sent to <strong>{phone}</strong>. Enter the 6-digit code below.
    </p>
    <div className="event-reg-form-group">
      <label className="event-reg-label" htmlFor="phone-code">
        Verification Code <span className="required-mark">*</span>
      </label>
      <input
        id="phone-code"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        className="event-reg-input"
        value={phoneCode}
        onChange={(e) => onCodeChange(e.target.value.replace(/\D/g, ''))}
        placeholder="123456"
        required
      />
    </div>
    <button type="submit" className="event-reg-submit" disabled={verifying || phoneCode.length !== 6}>
      {verifying ? <><span className="event-reg-spinner" /> Verifying...</> : 'Verify Phone'}
    </button>
    <p className="event-reg-resend">
      Didn't receive the code?{' '}
      <button type="button" className="event-reg-link-button" onClick={onResend} disabled={verifying}>
        Resend
      </button>
    </p>
  </form>
);
