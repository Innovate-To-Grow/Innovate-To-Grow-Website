type PastProjectsAIStatusTone = 'error' | 'loading' | 'success';

interface PastProjectsAIStatusProps {
  message: string;
  tone: PastProjectsAIStatusTone;
}

export const PastProjectsAIStatus = ({message, tone}: PastProjectsAIStatusProps) => (
  <div
    className={`past-projects-ai-search-message is-${tone}`}
    role={tone === 'error' ? 'alert' : 'status'}
    aria-live={tone === 'error' ? 'assertive' : 'polite'}
  >
    <div className="past-projects-ai-search-message-content">
      {tone === 'loading' ? <span className="past-projects-ai-search-spinner" aria-hidden="true" /> : null}
      <span>{message}</span>
    </div>
    {tone === 'loading' ? (
      <span className="past-projects-ai-search-progress" aria-hidden="true">
        <span />
      </span>
    ) : null}
  </div>
);
