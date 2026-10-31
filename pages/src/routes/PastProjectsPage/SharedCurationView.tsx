import {useCallback} from 'react';
import {Link} from 'react-router';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {MergedResultsTable, SharedPastProjectMergeSearch, type ProjectGridItem} from '@/features/projects';
import {DEFAULT_PAST_PROJECT_SHARE_NAME, type PastProjectShare, type ProjectGridRow} from '@/features/projects/api';
import {ALL_PROJECTS_CATALOG, PAST_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext, type ProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import {curationBranding} from '@/features/projects/components/merged/list/curationBranding';
import {useRetryInPlace} from '@/features/projects/components/shared/utils/useRetryInPlace';
import {SharedListLoadFailed, SharedListUnavailable} from './SharedListMessages';
import {shareDisplayTitle} from './useSharedListMutations';

interface SharedCurationViewProps {
  status: {loading: boolean; error: string | null; notFound: boolean; retry: () => void};
  conflictMessage: string | null;
  /** Arrived from the builder's save. */
  justSaved: boolean;
  /** The builder that saved it, which the saved notice names and links to. Past Projects when not given. */
  builtOn?: Pick<ProjectCatalog, 'path' | 'title'>;
  share: PastProjectShare | null;
  items: ProjectGridItem[];
  onUpdateShare: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  /** Every project (All Projects' list), for the owner's "add more projects" search. */
  projects: {rows: ProjectGridRow[]; loading: boolean; error: string | null; refetch: () => void};
  onAddRows: (rows: ProjectGridRow[]) => Promise<number>;
}

type SharedCurationContentProps = Omit<SharedCurationViewProps, 'status' | 'conflictMessage'>;

/**
 * The loaded list: the saved notice, the list itself, the owner's search for more projects, and a pointer to the
 * builder. The owner's search runs over every project (All Projects), so it words itself as All Projects does. The
 * pointer names the list the curation's projects come from (curationBranding): All Projects once it holds a
 * current-semester project.
 */
const SharedCurationContent = ({
  justSaved,
  builtOn = PAST_PROJECTS_CATALOG,
  share,
  items,
  onUpdateShare,
  projects,
  onAddRows,
}: SharedCurationContentProps) => {
  const canEdit = Boolean(share?.can_edit);
  const searchLink = curationBranding(share?.rows ?? []).searchLink;
  return (
    <>
      {justSaved && canEdit ? (
        <p className="itg-notice past-projects-saved-notice" role="status">
          Curation saved. It is listed under My Curations on the <Link to={builtOn.path}>{builtOn.title}</Link> page,
          and you can keep editing it here.
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
        <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>
          <SharedPastProjectMergeSearch
            currentRows={share.rows}
            error={projects.error}
            loading={projects.loading}
            rows={projects.rows}
            onAddRows={onAddRows}
            onRefreshRows={projects.refetch}
          />
        </ProjectCatalogContext.Provider>
      ) : null}
      <p className="past-projects-shared-closing">
        Want to make your own list? <Link to={searchLink.to}>{searchLink.label}</Link>
      </p>
    </>
  );
};

/** A saved curation's shared page; its owner can edit it and add more projects. */
export const SharedCurationView = ({
  status,
  conflictMessage,
  justSaved,
  builtOn,
  share,
  items,
  onUpdateShare,
  projects,
  onAddRows,
}: SharedCurationViewProps) => {
  // A retry that brings the curation moves focus from the gone Try Again to its title (focusable).
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
      {/* Kept in the page while empty, so screen readers announce "Loading curation…" when it is put in. */}
      <p className="past-projects-state past-projects-loading-line" role="status">
        {status.loading && !loadFailure.showFailure ? <LoadingIndicator label="Loading curation…" /> : null}
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
          builtOn={builtOn}
          share={share}
          items={items}
          onUpdateShare={onUpdateShare}
          projects={projects}
          onAddRows={onAddRows}
        />
      ) : null}
    </div>
  );
};
