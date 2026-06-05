import {useEffect, useMemo, useState} from 'react';
import {useParams} from 'react-router-dom';
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
  const sharedMode = Boolean(shareId);
  const {share, loading: shareLoading, error: shareError} = usePastProjectShareData(shareId);
  const [editableShare, setEditableShare] = useState<PastProjectShare | null>(null);
  const activeShare = editableShare?.id === shareId ? editableShare : share;
  const {rows, loading, error} = usePastProjectGridData(!sharedMode || Boolean(activeShare?.can_edit));

  useEffect(() => {
    setEditableShare(share);
  }, [share]);

  const sharedItems = useMemo(
    () => createProjectGridItems(activeShare?.rows || [], `shared-${shareId || 'past-projects'}`),
    [activeShare?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: typeof rows, name: string, note: string) => {
    const created = await createPastProjectShare(shareRows, name, note);
    return new URL(`/past-projects/${created.id}`, window.location.origin).toString();
  };

  const handleUpdateShare = async (shareRows: ProjectGridRow[], note: string, name: string) => {
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
            Search across past Innovate to Grow projects, keep only the rows you want, and merge the results into a
            shareable archive.
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
          onCreateShare={handleCreateShare}
        />
      )}
    </div>
  );
};
