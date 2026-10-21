export const CMSPageLoading = () => (
  <div className="cms-page-shell cms-page-loading" aria-busy="true">
    <div role="status" aria-label="Loading page content" className="cms-page-status">
      <span className="cms-page-status-text">Loading page content</span>
    </div>
    <div className="cms-page-skeleton cms-page-skeleton-hero" aria-hidden="true" />
    <div className="cms-page-skeleton" aria-hidden="true" />
    <div className="cms-page-skeleton" aria-hidden="true" />
  </div>
);

/** A page that failed to load; with `onRetry`, it offers to try again. */
export const CMSPageError = ({onRetry}: {onRetry?: () => void}) => (
  <div className="cms-page-error" role="alert">
    <p className="cms-page-error-text">Something went wrong loading this page.</p>
    {onRetry ? (
      <div className="cms-page-error-actions">
        <button type="button" className="itg-btn itg-btn-outline" onClick={onRetry}>Try again</button>
      </div>
    ) : null}
  </div>
);
