import {useMemo} from 'react';
import {useParams, useSearchParams} from 'react-router-dom';
import {MergedResultsTable, PastProjectsBuilder, createProjectGridItems} from '@/features/projects';
import {usePastProjectGridData, usePastProjectShareData} from '@/features/projects/hooks/useProjectGridData';
import {createPastProjectShare} from '@/features/projects/api';
import {formatSemesterLabel, semesterParamToLabel} from '@/lib/semester';

export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const sharedMode = Boolean(shareId);
  const {rows, loading, error} = usePastProjectGridData(!sharedMode);
  const {share, loading: shareLoading, error: shareError} = usePastProjectShareData(shareId);
  const sharedItems = useMemo(
    () => createProjectGridItems(share?.rows || [], `shared-${shareId || 'past-projects'}`),
    [share?.rows, shareId],
  );

  // Optional `?semester=2024-fall` filter — lets past-event pages link to a
  // single semester's projects while keeping the full search/sort/expand UI.
  const [searchParams] = useSearchParams();
  const semesterLabel = useMemo(() => {
    const param = searchParams.get('semester');
    return param ? semesterParamToLabel(param) : null;
  }, [searchParams]);
  const filteredRows = useMemo(() => {
    if (!semesterLabel) {
      return rows;
    }
    const target = semesterLabel.toLowerCase();
    return rows.filter((row) => formatSemesterLabel(row.semester_label).toLowerCase() === target);
  }, [rows, semesterLabel]);

  const handleCreateShare = async (shareRows: typeof rows) => {
    const created = await createPastProjectShare(shareRows);
    return new URL(`/past-projects/${created.id}`, window.location.origin).toString();
  };

  return (
    <div className="past-projects-page">
      <header className="past-projects-hero">
        <h1 className="past-projects-title">
          {!sharedMode && semesterLabel ? `Past Projects — ${semesterLabel}` : 'Past Projects'}
        </h1>
        <p className="past-projects-lead">
          {sharedMode
            ? 'This shared view shows a saved set of merged past project results.'
            : semesterLabel
              ? `Search ${semesterLabel} Innovate to Grow projects, keep only the rows you want, and merge the results into a shareable archive.`
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
          rows={filteredRows}
          loading={loading}
          error={error}
          onCreateShare={handleCreateShare}
        />
      )}
    </div>
  );
};
