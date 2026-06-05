import {useMemo} from 'react';
import {useParams} from 'react-router-dom';
import {MergedResultsTable, PastProjectsBuilder, createProjectGridItems} from '@/features/projects';
import {usePastProjectGridData, usePastProjectShareData} from '@/features/projects/hooks/useProjectGridData';
import {createPastProjectShare} from '@/features/projects/api';

export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const sharedMode = Boolean(shareId);
  const {rows, loading, error} = usePastProjectGridData(!sharedMode);
  const {share, loading: shareLoading, error: shareError} = usePastProjectShareData(shareId);
  const sharedItems = useMemo(
    () => createProjectGridItems(share?.rows || [], `shared-${shareId || 'past-projects'}`),
    [share?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: typeof rows, name: string, note: string) => {
    const created = await createPastProjectShare(shareRows, name, note);
    return new URL(`/past-projects/${created.id}`, window.location.origin).toString();
  };

  return (
    <div className="past-projects-page">
      <header className="past-projects-hero">
        <h1 className="past-projects-title">Past Projects</h1>
        <p className="past-projects-lead">
          {sharedMode
            ? 'This shared view shows a saved set of merged past project results.'
            : 'Search across past Innovate to Grow projects, keep only the rows you want, and merge the results into a shareable archive.'}
        </p>
      </header>

      {sharedMode ? (
        <>
          {shareLoading ? <div className="past-projects-state">Loading shared results...</div> : null}
          {shareError ? <div className="past-projects-state past-projects-state-error">{shareError}</div> : null}
          {!shareLoading && !shareError ? (
            <MergedResultsTable
              rows={sharedItems}
              sharedMode
              note={share?.note}
              title="Shared Past Project Results"
            />
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
