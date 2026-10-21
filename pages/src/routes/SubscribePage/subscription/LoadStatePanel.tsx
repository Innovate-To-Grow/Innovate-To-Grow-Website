interface LoadStatePanelProps {
  failed: boolean;
  errorMessage: string | null;
  loadingMessage: string;
  onRetry: () => void;
}

/** A step's data is still loading, or failed with a Retry button. */
export const LoadStatePanel = ({failed, errorMessage, loadingMessage, onRetry}: LoadStatePanelProps) =>
  failed ? (
    <div className="itg-panel subscribe-section" role="alert">
      <p className="subscribe-hint">{errorMessage}</p>
      <button type="button" className="itg-btn itg-btn-primary subscribe-submit" onClick={onRetry}>
        Retry
      </button>
    </div>
  ) : (
    <div className="itg-panel subscribe-section" role="status">
      <p className="subscribe-hint">{loadingMessage}</p>
    </div>
  );
