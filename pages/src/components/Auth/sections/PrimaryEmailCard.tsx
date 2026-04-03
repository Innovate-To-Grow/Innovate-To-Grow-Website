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
      <div style={{flex: 1, minWidth: 0}}>
        <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap'}}>
          <span style={{fontWeight: 600, color: '#1f2937', wordBreak: 'break-all'}}>{profile.email}</span>
          <span className="email-center-badge primary">Primary</span>
          <span className={`email-center-badge ${profile.email_verified ? 'verified' : 'unverified'}`}>
            {profile.email_verified ? 'Verified' : 'Unverified'}
          </span>
        </div>
        <div className="email-center-actions">
          <label className="email-center-toggle" aria-label="Subscribe primary email">
            <input type="checkbox" checked={profile.email_subscribe} onChange={onToggleSubscribe} disabled={subscribeSaving} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Subscribe</span>
          </label>
          {!profile.email_verified && profile.primary_email_id ? (
            <button type="button" className="email-center-btn verify" onClick={onToggleVerify}>
              Verify
            </button>
          ) : null}
        </div>
      </div>
    </div>

    {verifying && !profile.email_verified ? (
      <div className="email-center-verify-inline">
        <form onSubmit={onVerifySubmit} className="email-center-verify-form">
          <CodeInput value={verifyCode} onChange={onVerifyCodeChange} disabled={verifyLoading} />
          <div style={{display: 'flex', gap: '0.5rem', flexWrap: 'wrap'}}>
            <button
              type="submit"
              className="auth-form-submit"
              disabled={verifyLoading || verifyCode.length !== 6}
              style={{flex: 1, marginTop: 0, fontSize: '0.875rem', padding: '0.625rem 1rem'}}
            >
              {verifyLoading ? <><span className="auth-spinner" /> Verifying...</> : 'Submit Code'}
            </button>
            <button
              type="button"
              className="email-center-btn verify"
              disabled={resendLoading}
              onClick={onResend}
              style={{fontSize: '0.8125rem'}}
            >
              {resendLoading ? 'Sending...' : 'Resend Code'}
            </button>
            <button
              type="button"
              className="email-center-btn delete"
              onClick={onCancelVerify}
              style={{fontSize: '0.8125rem'}}
            >
              Cancel
            </button>
          </div>
        </form>
        {verifyError ? <StatusAlert tone="error" message={verifyError} style={{marginTop: '0.5rem'}} /> : null}
      </div>
    ) : null}
  </div>
);
