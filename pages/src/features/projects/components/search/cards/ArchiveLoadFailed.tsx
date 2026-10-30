interface ArchiveLoadFailedProps {
  /** Loads the archive again; left out, no retry is offered. */
  onRetry?: () => void;
}

/** The past-project archive did not load, so no search table can open: say so plainly and offer to try again. */
export const ArchiveLoadFailed = ({onRetry}: ArchiveLoadFailedProps) => (
  <div className="past-projects-archive-failed" role="alert">
    <p className="project-grid-state project-grid-state-error itg-error">
      The past-project archive could not be loaded. Check your connection and try again.
    </p>
    {onRetry ? (
      <button type="button" className="itg-btn itg-btn-primary" onClick={onRetry}>
        Try again
      </button>
    ) : null}
  </div>
);
