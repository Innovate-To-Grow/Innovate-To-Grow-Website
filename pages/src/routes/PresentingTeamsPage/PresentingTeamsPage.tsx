import {useMemo} from 'react';
import {Link} from 'react-router';
import {CurrentProjectsView} from '@/features/projects/components/views/pages/CurrentProjectsView';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

export const PresentingTeamsPage = () => {
  const {rows, loading, error, refetch, classLabels} = useCurrentProjectGridData();
  const presentingRows = useMemo(() => rows.filter((row) => row.is_presenting === 'Yes'), [rows]);

  return (
    <CurrentProjectsView
      title="Presenting Teams"
      lede="Teams presenting at this semester's Innovate to Grow showcase. Search by project title, team, organization, industry or student name, and open a project to read its abstract and team members."
      rows={presentingRows}
      loading={loading}
      error={error}
      onRetry={refetch}
      classLabels={classLabels}
      namespace="presenting-teams"
      emptyTitle="No presenting teams yet"
      emptyMessage="Teams appear here once this semester's showcase schedule is published. Older projects are in Past Projects."
      emptyActions={
        <Link className="itg-btn itg-btn-outline" to="/past-projects">
          Search Past Projects
        </Link>
      }
      countLabel="teams"
    />
  );
};
