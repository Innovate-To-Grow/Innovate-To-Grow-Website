import {useMemo} from 'react';
import {useParams} from 'react-router-dom';
import {MergedResultsTable, PastProjectsBuilder, createProjectGridItems} from '../../components/Projects';
import {usePastProjectGridData, usePastProjectShareData} from '../../hooks/useProjectGridData';
import {createPastProjectShare} from '../../features/projects/api';

export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const sharedMode = Boolean(shareId);
  const {rows, loading, error} = usePastProjectGridData(!sharedMode);
  const {share, loading: shareLoading, error: shareError} = usePastProjectShareData(shareId);
  const sharedItems = useMemo(
    () => createProjectGridItems(share?.rows || [], `shared-${shareId || 'past-projects'}`),
    [share?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: typeof rows) => {
    const created = await createPastProjectShare(shareRows);
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
