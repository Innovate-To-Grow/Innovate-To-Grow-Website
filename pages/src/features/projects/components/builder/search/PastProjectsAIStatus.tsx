export type PastProjectsStatusTone = 'error' | 'info' | 'loading' | 'success';

interface PastProjectsAIStatusProps {
  message: string;
  tone: PastProjectsStatusTone;
  /**
   * Make this element a live region (role=status, or role=alert for errors). Turn it off when a
   * persistent live region elsewhere already announces the message.
   */
  announce?: boolean;
}

function StatusCheckIcon() {
  return (
    <svg className="past-projects-status-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}

// Status line for AI search and for per-table saves.
export const PastProjectsAIStatus = ({message, tone, announce = true}: PastProjectsAIStatusProps) => (
  <div
    className={`past-projects-ai-search-message is-${tone}`}
    role={announce ? (tone === 'error' ? 'alert' : 'status') : undefined}
    aria-live={announce ? (tone === 'error' ? 'assertive' : 'polite') : undefined}
  >
    <div className="past-projects-ai-search-message-content">
      {tone === 'success' ? <StatusCheckIcon /> : null}
      <span>{message}</span>
    </div>
  </div>
);
