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
      <span>{message}</span>
    </div>
  </div>
);
