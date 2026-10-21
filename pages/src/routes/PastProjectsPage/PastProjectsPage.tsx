import {useMemo} from 'react';
import {useLocation, useNavigate, useParams, useSearchParams} from 'react-router';
import {MyCurationsPanel, PastProjectsBuilder, createProjectGridItems} from '@/features/projects';
import {getEarliestTermYear} from '@/features/projects/components/projectGrid';
import {usePastProjectGridData, usePastProjectShareData} from '@/features/projects/hooks/useProjectGridData';
import {createPastProjectShare} from '@/features/projects/api';
import {usePageTitle} from '@/hooks/usePageTitle';
import {SharedCurationView} from './SharedCurationView';
import {shareDisplayTitle, useSharedListMutations} from './useSharedListMutations';

/**
 * `/past-projects` (the builder) and `/past-projects/:shareId` (a saved curation's shared page). Edits to a
 * shared page go through `useSharedListMutations`, which serializes them and reconciles concurrent edits.
 */
export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const navigate = useNavigate();
  // Set by the builder's save, which opens the new curation's page.
  const justSaved = Boolean((useLocation().state as {curationSaved?: boolean} | null)?.curationSaved);
  const [searchParams] = useSearchParams();
  const sharedMode = Boolean(shareId);
  const {
    share,
    loading: shareLoading,
    error: shareError,
    notFound: shareNotFound,
    retry: retryShare,
  } = usePastProjectShareData(shareId);
  const {activeShare, setEditableShare, conflictMessage, updateShare, addShareRows} = useSharedListMutations(
    shareId,
    share,
  );
  // A shared list is named after the share; the plain page keeps its route title.
  usePageTitle(sharedMode && activeShare ? shareDisplayTitle(activeShare) : null);
  // The archive is only needed to search (the builder, or the owner adding to a shared list).
  const {rows, loading, error, refetch} = usePastProjectGridData(!sharedMode || Boolean(activeShare?.can_edit));

  const sharedItems = useMemo(
    () => createProjectGridItems(activeShare?.rows || [], `shared-${shareId || 'past-projects'}`),
    [activeShare?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: typeof rows, name: string, note: string) => {
    const nextShare = await createPastProjectShare(shareRows, name, note);
    setEditableShare(nextShare);
    navigate(`/past-projects/${nextShare.id}`, {state: {curationSaved: true}});
    return nextShare;
  };

  const sinceYear = useMemo(() => getEarliestTermYear(rows), [rows]);
  const archiveMeta = rows.length
    ? `${rows.length} ${rows.length === 1 ? 'project' : 'projects'}${sinceYear ? ` since ${sinceYear}` : ''}`
    : '';

  if (sharedMode) {
    return (
      <SharedCurationView
        status={{loading: shareLoading, error: shareError, notFound: shareNotFound, retry: retryShare}}
        conflictMessage={conflictMessage}
        justSaved={justSaved}
        share={activeShare}
        items={sharedItems}
        onUpdateShare={updateShare}
        archive={{rows, loading, error, refetch}}
        onAddRows={addShareRows}
      />
    );
  }

  return (
    <div className="past-projects-page">
      <header className="past-projects-header">
        <h1 className="itg-page-title">Past Projects</h1>
        {archiveMeta ? <p className="itg-page-meta">{archiveMeta}</p> : null}
        <p className="itg-lead">
          Search past Innovate to Grow projects, check the ones you want, and collect them into a curation. Save it to
          keep it and share it with a link, or export it.
        </p>
      </header>

      <MyCurationsPanel />

      <PastProjectsBuilder
        rows={rows}
        loading={loading}
        error={error}
        initialSearch={searchParams.get('value') || ''}
        onRefreshRows={refetch}
        onCreateShare={handleCreateShare}
      />
    </div>
  );
};
