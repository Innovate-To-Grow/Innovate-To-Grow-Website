import {useMemo, useState} from 'react';
import {useNavigate, useParams} from 'react-router-dom';
import {
  MergedResultsTable,
  PastProjectsBuilder,
  SharedPastProjectMergeSearch,
  createProjectGridItems,
} from '@/features/projects';
import {usePastProjectGridData, usePastProjectShareData} from '@/features/projects/hooks/useProjectGridData';
import {createPastProjectShare, updatePastProjectShare, type PastProjectShare, type ProjectGridRow} from '@/features/projects/api';

export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const navigate = useNavigate();
  const sharedMode = Boolean(shareId);
  const {share, loading: shareLoading, error: shareError} = usePastProjectShareData(shareId);
  const [editableShare, setEditableShare] = useState<PastProjectShare | null>(null);
  // Reset the local override to the freshly fetched share whenever `share` changes identity.
  // This is the render-phase equivalent of the old `useEffect(() => setEditableShare(share), [share])`
  // (https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes):
  // `activeShare` already falls back to `share` when the override is stale, so the rendered output is
  // unchanged, but this avoids the effect's extra cascading commit.
  const [prevShare, setPrevShare] = useState(share);
  if (share !== prevShare) {
    setPrevShare(share);
    setEditableShare(share);
  }
  const activeShare = editableShare?.id === shareId ? editableShare : share;
  const {rows, loading, error, refetch} = usePastProjectGridData(!sharedMode || Boolean(activeShare?.can_edit));

  const sharedItems = useMemo(
    () => createProjectGridItems(activeShare?.rows || [], `shared-${shareId || 'past-projects'}`),
    [activeShare?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: typeof rows, name: string, note: string) => {
    const nextShare = await createPastProjectShare(shareRows, name, note);
    setEditableShare(nextShare);
    navigate(`/past-projects/${nextShare.id}`);
    return nextShare;
  };

  const handleUpdateShare = async (shareRows: ProjectGridRow[], name: string, note: string) => {
    if (!activeShare) {
      throw new Error('Shared past projects are not loaded yet.');
    }
    const updated = await updatePastProjectShare(activeShare.id, {rows: shareRows, note, name});
    setEditableShare(updated);
  };

  const handleAddShareRows = async (rowsToAdd: ProjectGridRow[]) => {
    if (!activeShare) {
      throw new Error('Shared past projects are not loaded yet.');
    }
    const updated = await updatePastProjectShare(activeShare.id, {
      rows: [...activeShare.rows, ...rowsToAdd],
      note: activeShare.note ?? '',
      name: activeShare.name,
    });
    setEditableShare(updated);
  };

  return (
    <div className="past-projects-page">
      <header className="past-projects-hero">
        <h1 className="past-projects-title">Past Projects</h1>
        {!sharedMode ? (
          <p className="past-projects-lead">
            Search across past Innovate to Grow projects, keep only the items you want, merge the selected results into
            a shareable archive, and curate the results.
          </p>
        ) : null}
      </header>

      {sharedMode ? (
        <>
          {shareLoading ? <div className="past-projects-state">Loading shared results...</div> : null}
          {shareError ? <div className="past-projects-state past-projects-state-error">{shareError}</div> : null}
          {!shareLoading && !shareError ? (
            <>
              <MergedResultsTable
                rows={sharedItems}
                sharedMode
                note={activeShare?.note}
                title={activeShare?.name?.trim() || 'Shared Past Project Results'}
                editable={Boolean(activeShare?.can_edit)}
                onUpdateShare={activeShare?.can_edit ? handleUpdateShare : undefined}
              />
              {activeShare?.can_edit ? (
                <SharedPastProjectMergeSearch
                  currentRows={activeShare.rows}
                  error={error}
                  loading={loading}
                  rows={rows}
                  onAddRows={handleAddShareRows}
                  onRefreshRows={refetch}
                />
              ) : null}
            </>
          ) : null}
        </>
      ) : (
        <PastProjectsBuilder
          rows={rows}
          loading={loading}
          error={error}
          onRefreshRows={refetch}
          onCreateShare={handleCreateShare}
        />
      )}
    </div>
  );
};
