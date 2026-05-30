import {useState, type FormEvent} from 'react';
import {CodeInput} from '../../forms/CodeInput';
import {StatusAlert} from '../../shared/StatusAlert';

interface DeleteAccountSectionProps {
  deleteCodeRequested: boolean;
  deleteCode: string;
  deleteVerificationToken: string | null;
  deleteLoading: boolean;
  deleteMessage: string | null;
  deleteError: string | null;
  onDeleteRequestCode: () => void;
  onDeleteVerifyCode: (event: FormEvent) => void;
  onDeleteConfirm: (event: FormEvent) => void;
  onDeleteCodeChange: (value: string) => void;
}

export const DeleteAccountSection = ({
  deleteCodeRequested,
  deleteCode,
  deleteVerificationToken,
  deleteLoading,
  deleteMessage,
  deleteError,
  onDeleteRequestCode,
  onDeleteVerifyCode,
  onDeleteConfirm,
  onDeleteCodeChange,
}: DeleteAccountSectionProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="account-section account-danger-section">
      <button
        type="button"
        className="account-section-header account-danger-toggle"
        onClick={() => setIsExpanded((current) => !current)}
        aria-expanded={isExpanded}
      >
        <h2 className="account-section-title">Delete Account</h2>
        <span className="account-section-toggle" aria-hidden="true">
          {isExpanded ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M2 7h12v2H2z"/></svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M7 2h2v5h5v2H9v5H7V9H2V7h5z"/></svg>
          )}
        </span>
      </button>

      {isExpanded ? (
        <div className="account-danger-content">
          {deleteMessage ? <StatusAlert tone="success" message={deleteMessage} style={{marginTop: '0.25rem'}} /> : null}
          {deleteError ? <StatusAlert tone="error" message={deleteError} style={{marginTop: '0.25rem'}} /> : null}

          <div className="account-danger-header">
            <p className="account-danger-help">This permanently deletes your account and connected data.</p>
            {!deleteCodeRequested && !deleteVerificationToken ? (
              <button
                type="button"
                className="account-danger-button"
                onClick={onDeleteRequestCode}
                disabled={deleteLoading}
              >
                {deleteLoading ? 'Sending...' : 'Send Deletion Code'}
              </button>
            ) : null}
          </div>

          {deleteCodeRequested && !deleteVerificationToken ? (
            <form className="account-password-form" onSubmit={onDeleteVerifyCode}>
              <div className="auth-form-group">
                <label className="auth-form-label" htmlFor="account-delete-code">Deletion Code</label>
                <CodeInput value={deleteCode} onChange={onDeleteCodeChange} disabled={deleteLoading} />
              </div>
              <div className="account-action-row">
                <button
                  type="submit"
                  className="account-danger-button"
                  disabled={deleteLoading || deleteCode.length !== 6}
                >
                  {deleteLoading ? 'Verifying...' : 'Verify Code'}
                </button>
              </div>
            </form>
          ) : null}

          {deleteVerificationToken ? (
            <form className="account-password-form" onSubmit={onDeleteConfirm}>
              <p className="account-danger-confirmation">
                Your code has been verified. Deleting your account cannot be undone.
              </p>
              <div className="account-action-row">
                <button type="submit" className="account-danger-button" disabled={deleteLoading}>
                  {deleteLoading ? 'Deleting...' : 'Delete Account'}
                </button>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
