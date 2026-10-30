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
      emptyMessage="No current projects are available yet."
      countLabel="projects"
    />
  );
};
