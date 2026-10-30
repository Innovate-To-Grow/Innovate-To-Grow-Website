import {useCallback} from 'react';
import {Link} from 'react-router';
import {MergedResultsTable, SharedPastProjectMergeSearch, type ProjectGridItem} from '@/features/projects';
import {DEFAULT_PAST_PROJECT_SHARE_NAME, type PastProjectShare, type ProjectGridRow} from '@/features/projects/api';
import {useRetryInPlace} from '@/features/projects/components/shared/utils/useRetryInPlace';
import {SharedListLoadFailed, SharedListUnavailable} from './SharedListMessages';
import {shareDisplayTitle} from './useSharedListMutations';

interface SharedCurationViewProps {
  status: {loading: boolean; error: string | null; notFound: boolean; retry: () => void};
  conflictMessage: string | null;
  /** Arrived from the builder's save. */
  justSaved: boolean;
  share: PastProjectShare | null;
  items: ProjectGridItem[];
  onUpdateShare: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  /** The past-project archive, for the owner's "add more projects" search. */
  archive: {rows: ProjectGridRow[]; loading: boolean; error: string | null; refetch: () => void};
  onAddRows: (rows: ProjectGridRow[]) => Promise<number>;
}

type SharedCurationContentProps = Omit<SharedCurationViewProps, 'status' | 'conflictMessage'>;

/** The loaded list: the saved notice, the list itself, the owner's archive search, and a pointer to the builder. */
const SharedCurationContent = ({justSaved, share, items, onUpdateShare, archive, onAddRows}: SharedCurationContentProps) => {
  const canEdit = Boolean(share?.can_edit);
  return (
    <>
      {justSaved && canEdit ? (
        <p className="itg-notice past-projects-saved-notice" role="status">
          Curation saved. It is listed under My Curations on the{' '}
          <Link to="/past-projects">Past Projects</Link> page, and you can keep editing it here.
        </p>
      ) : null}
      <MergedResultsTable
        rows={items}
        sharedMode
        note={share?.note}
        title={share ? shareDisplayTitle(share) : DEFAULT_PAST_PROJECT_SHARE_NAME}
        sharedAt={share?.created_at}
        editable={canEdit}
        onUpdateShare={canEdit ? onUpdateShare : undefined}
      />
      {share && canEdit ? (
        <SharedPastProjectMergeSearch
          currentRows={share.rows}
          error={archive.error}
          loading={archive.loading}
          rows={archive.rows}
          onAddRows={onAddRows}
          onRefreshRows={archive.refetch}
        />
      ) : null}
      <p className="past-projects-shared-closing">
        Want to make your own list? <Link to="/past-projects">Search all past projects</Link>
      </p>
    </>
  );
};

/** A saved curation's shared page; its owner can edit it and add projects from the archive. */
export const SharedCurationView = ({
  status,
  conflictMessage,
  justSaved,
  share,
  items,
  onUpdateShare,
  archive,
  onAddRows,
}: SharedCurationViewProps) => {
  // A retry that brings the curation moves focus from the gone Try again to its title (focusable).
  const focusTitle = useCallback(
    () => document.querySelector<HTMLElement>('.past-projects-page--shared h1[tabindex]'),
    [],
  );
  const loadFailure = useRetryInPlace({
    loading: status.loading,
    // "Isn't available" only when the API says the list does not exist; any other failure may pass.
    failed: Boolean(status.error) && !status.notFound,
    onRetry: status.retry,
    focusTarget: focusTitle,
  });

  return (
    <div className="past-projects-page past-projects-page--shared">
      {/* Kept in the page while empty, so screen readers announce "Loading curation..." when it is put in. */}
      <p className="past-projects-state past-projects-loading-line" role="status">
        {status.loading && !loadFailure.showFailure ? 'Loading curation...' : null}
      </p>
      {status.error && status.notFound ? <SharedListUnavailable /> : null}
      {loadFailure.showFailure ? (
        <SharedListLoadFailed retrying={loadFailure.retrying} onRetry={loadFailure.retry} />
      ) : null}
      {conflictMessage ? (
        <p className="past-projects-state past-projects-state-error itg-error" role="alert">
          {conflictMessage}
        </p>
      ) : null}
      {!status.loading && !status.error ? (
        <SharedCurationContent
          justSaved={justSaved}
          share={share}
          items={items}
          onUpdateShare={onUpdateShare}
          archive={archive}
          onAddRows={onAddRows}
        />
      ) : null}
    </div>
  );
};
