import type {FormEvent} from 'react';
import type {ProfileResponse} from '../../../services/auth';
import {CodeInput} from '../forms/CodeInput';
import {StatusAlert} from '../shared/StatusAlert';

interface PrimaryEmailCardProps {
  profile: ProfileResponse;
  subscribeSaving: boolean;
  verifying: boolean;
  verifyCode: string;
  verifyLoading: boolean;
  verifyError: string | null;
  resendLoading: boolean;
  onToggleSubscribe: () => void;
  onToggleVerify: () => void;
  onVerifyCodeChange: (value: string) => void;
  onVerifySubmit: (event: FormEvent) => void;
  onResend: () => void;
  onCancelVerify: () => void;
}

export const PrimaryEmailCard = ({
  profile,
  subscribeSaving,
  verifying,
  verifyCode,
  verifyLoading,
  verifyError,
  resendLoading,
  onToggleSubscribe,
  onToggleVerify,
  onVerifyCodeChange,
  onVerifySubmit,
  onResend,
  onCancelVerify,
}: PrimaryEmailCardProps) => (
  <div className="email-center-card">
    <div className="email-center-row">
      <div className="email-center-card-main">
        <div className="email-center-card-heading">
          <span className="email-center-card-title email-center-card-title--emphasis">{profile.email}</span>
          <span className="email-center-badge primary">Primary</span>
          <span className={`email-center-badge ${profile.email_verified ? 'verified' : 'unverified'}`}>
            {profile.email_verified ? 'Verified' : 'Unverified'}
          </span>
        </div>
        <div className="email-center-actions">
          <label className="email-center-toggle" aria-label="Subscribe primary email">
            <input type="checkbox" checked={profile.email_subscribe} onChange={onToggleSubscribe} disabled={subscribeSaving} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Newsletters</span>
          </label>
          {!profile.email_verified && profile.primary_email_id && !verifying ? (
            <button type="button" className="email-center-btn verify" disabled={resendLoading} onClick={onToggleVerify}>
              Verify
            </button>
          ) : null}
        </div>
      </div>
    </div>

    {verifying && !profile.email_verified ? (
      <div className="email-center-verify-inline">
        <p className="email-center-verify-hint">
          Enter the 6-digit code we sent to this address, then tap Submit code.
        </p>
        <form onSubmit={onVerifySubmit} className="email-center-verify-form">
          <div className="email-center-verify-code-wrap">
            <CodeInput value={verifyCode} onChange={onVerifyCodeChange} disabled={verifyLoading} />
          </div>
          <div className="email-center-verify-actions">
            <button
              type="submit"
              className="auth-form-submit account-action-primary email-center-verify-submit"
              disabled={verifyLoading || verifyCode.length !== 6}
            >
              {verifyLoading ? <><span className="auth-spinner" /> Submitting...</> : 'Submit code'}
            </button>
            <div className="email-center-verify-secondary-row">
              <button
                type="button"
                className="email-center-btn verify email-center-verify-secondary-btn"
                disabled={resendLoading}
                onClick={onResend}
              >
                {resendLoading ? 'Sending...' : 'Resend Code'}
              </button>
              <button
                type="button"
                className="email-center-btn delete email-center-verify-secondary-btn"
                onClick={onCancelVerify}
              >
                Cancel
              </button>
            </div>
          </div>
        </form>
        {verifyError ? (
          <div className="email-center-verify-alert">
            <StatusAlert tone="error" message={verifyError} />
          </div>
        ) : null}
      </div>
    ) : null}
  </div>
);
