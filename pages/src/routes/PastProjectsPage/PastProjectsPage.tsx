import {PastProjectsBuilder} from '@/features/projects';
import {usePastProjectGridData} from '@/features/projects/hooks/useProjectGridData';

export const PastProjectsPage = () => {
  const {rows, loading, error, refetch} = usePastProjectGridData();

  return (
    <div className="past-projects-page">
      <header className="past-projects-hero">
        <h1 className="past-projects-title">Past Projects</h1>
        <p className="past-projects-lead">
          Search across past Innovate to Grow projects, keep only the items you want, and merge the selected results
          into a curated archive.
        </p>
      </header>

      <PastProjectsBuilder
        rows={rows}
        loading={loading}
        error={error}
        onRefreshRows={refetch}
      />
    </div>
  );
};
