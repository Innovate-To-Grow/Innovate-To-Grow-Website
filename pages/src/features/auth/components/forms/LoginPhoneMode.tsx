import type { FormEvent, RefObject } from 'react';
import { PrivacyLegalNotice } from '../shared/PrivacyLegalNotice';
import {
  canSubmitNationalPhone,
  formatNationalInputDisplay,
  nationalInputMaxLength,
} from '../sections/internal/phoneInput';

interface LoginPhoneModeProps {
  /** National digits only (e.g. "2025550123"). */
  phone: string;
  isLoading: boolean;
  phoneInputRef: RefObject<HTMLInputElement | null>;
  onPhoneChange: (nationalDigits: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSwitchToEmail: () => void;
}

export const LoginPhoneMode = ({
  phone,
  isLoading,
  phoneInputRef,
  onPhoneChange,
  onSubmit,
  onSwitchToEmail,
}: LoginPhoneModeProps) => {
  const canSubmit = canSubmitNationalPhone(phone);
  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <div className="auth-form-group">
        <label className="auth-form-label" htmlFor="login-phone">
          Phone number
        </label>
        <input
          ref={phoneInputRef}
          id="login-phone"
          type="tel"
          inputMode="tel"
          className="auth-form-input"
          value={formatNationalInputDisplay(phone)}
          onChange={(event) => onPhoneChange(event.target.value)}
          placeholder="(201)555-0123"
          maxLength={nationalInputMaxLength()}
          required
          autoComplete="tel-national"
        />
        <span className="auth-help-text">
          US numbers only. We&apos;ll text you a code to sign in, or start your account setup if it&apos;s new.
        </span>
      </div>

      <PrivacyLegalNotice />

      <button type="submit" className="auth-form-submit" disabled={isLoading || !canSubmit}>
        {isLoading ? (
          <>
            <span className="auth-spinner" />
            Sending code...
          </>
        ) : (
          'Continue with Phone'
        )}
      </button>

      <div style={{ textAlign: 'center' }}>
        <button type="button" className="auth-text-link" onClick={onSwitchToEmail} style={{ fontSize: '0.8125rem' }}>
          Use email instead
        </button>
      </div>
    </form>
  );
};
