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

// Status line for AI search and for per-table saves.
export const PastProjectsAIStatus = ({message, tone, announce = true}: PastProjectsAIStatusProps) => (
  <div
    className={`past-projects-ai-search-message is-${tone}`}
    role={announce ? (tone === 'error' ? 'alert' : 'status') : undefined}
    aria-live={announce ? (tone === 'error' ? 'assertive' : 'polite') : undefined}
  >
    <div className="past-projects-ai-search-message-content">
      <span>{message}</span>
    </div>
  </div>
);
