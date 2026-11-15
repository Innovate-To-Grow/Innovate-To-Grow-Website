

function LockIcon() {
  return (
    <svg
      className="past-projects-lock-icon"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="5" y="11" width="14" height="10" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

interface AISearchTableButtonProps {
  loginRequired: boolean;
  disabled: boolean;
  loginNoteId: string;
  onClick: () => void;
}

/** "+ AI Search Table", or a locked button pointing at the sign-in note. */
export const AISearchTableButton = ({loginRequired, disabled, loginNoteId, onClick}: AISearchTableButtonProps) => (
  <button
    type="button"
    className={`itg-btn itg-btn-primary past-projects-ai-table-button${
      loginRequired ? ' is-login-required' : ''
    }`}
    onClick={onClick}
    disabled={disabled}
    aria-describedby={loginRequired ? loginNoteId : undefined}
  >
    {loginRequired ? (
      <>
        <LockIcon />
        AI Search Table
      </>
    ) : (
      '+ AI Search Table'
    )}
  </button>
);
