import {Link} from 'react-router';
import {CurrentProjectsView} from '@/features/projects/components/views/pages/CurrentProjectsView';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

export const ProjectsPage = () => {
  const {rows, loading, error, refetch, classLabels} = useCurrentProjectGridData();

  return (
    <CurrentProjectsView
      title="Current Projects"
      lede="Browse this semester's Innovate to Grow projects. Search by project title, team, organization, industry or student name, and open a project to read its abstract and team members."
      rows={rows}
      loading={loading}
      error={error}
      onRetry={refetch}
      classLabels={classLabels}
      namespace="current-projects"
      emptyTitle="No current projects yet"
      emptyMessage="This semester's projects appear here once the schedule is published. Older projects are in Past Projects."
      emptyActions={
        <Link className="itg-btn itg-btn-outline" to="/past-projects">
          Search Past Projects
        </Link>
      }
      countLabel="projects"
    />
  );
};
