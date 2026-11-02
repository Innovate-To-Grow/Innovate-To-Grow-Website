import {useCallback} from 'react';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import {softDisabled} from '../../shared/utils/softDisabled';
import {useRetryInPlace} from '../../shared/utils/useRetryInPlace';

const NO_RETRY = () => {};

interface ArchiveLoadStateProps {
  loading: boolean;
  /** The archive's first load failed, so no search table can open (a failed refresh keeps the archive it had). */
  failed: boolean;
  /** Loads the archive again; left out, no retry is offered. */
  onRetry?: () => void;
  /** The section's heading, which takes focus when a retry brings the archive. */
  headingId: string;
  /**
   * The class that holds the first table's room, on the loading line and the failure (the builder's), so the page
   * below does not move when the load fails.
   */
  loadingClassName?: string;
}

/**
 * The archive's loading line and, when its first load failed, the failure with Try Again, in the words of the page's
 * list (ProjectCatalog: the archive, or All Projects' whole list). The loading line stays
 * in the page while empty, so screen readers announce "Loading…" when it is put in; empty, it takes no room. While
 * a retry runs the failure stays, saying it is loading (see useRetryInPlace), so a second failure is announced too.
 * Try Again is an outline button: the page around it keeps its own primary actions.
 */
export const ArchiveLoadState = ({loading, failed, onRetry, headingId, loadingClassName}: ArchiveLoadStateProps) => {
  const {copy} = useProjectCatalog();
  const focusHeading = useCallback(() => document.getElementById(headingId), [headingId]);
  const {retrying, showFailure, retry} = useRetryInPlace({
    loading,
    failed,
    onRetry: onRetry ?? NO_RETRY,
    focusTarget: focusHeading,
  });
  const loadingLine = loading && !showFailure;
  const roomClass = loadingClassName ? ` ${loadingClassName}` : '';

  return (
    <>
      <p className={`project-grid-state past-projects-loading-line${loadingLine ? roomClass : ''}`} role="status">
        {loadingLine ? <LoadingIndicator label={copy.loading} /> : null}
      </p>
      {showFailure ? (
        <div className={`past-projects-archive-failed${roomClass}`} role="alert">
          <p className={`project-grid-state${retrying ? '' : ' project-grid-state-error itg-error'}`}>
            {retrying ? <LoadingIndicator label={copy.loading} /> : copy.loadFailed}
          </p>
          {onRetry ? (
            <button type="button" className="itg-btn itg-btn-outline" {...softDisabled(retrying, retry)}>
              Try Again
            </button>
          ) : null}
        </div>
      ) : null}
    </>
  );
};
