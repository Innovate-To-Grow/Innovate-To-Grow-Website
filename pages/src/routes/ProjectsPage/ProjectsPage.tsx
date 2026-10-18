import {CurrentProjectsView} from '@/features/projects/components/CurrentProjectsView';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

export const ProjectsPage = () => {
  const {rows, loading, error, classLabels} = useCurrentProjectGridData();

  return (
    <CurrentProjectsView
      title="Current Projects"
      lede="Browse this semester's Innovate to Grow projects. Search by team, sponsor organization or industry, and open a project to read its abstract and team members."
      rows={rows}
      loading={loading}
      error={error}
      classLabels={classLabels}
      namespace="current-projects"
      emptyMessage="No current projects are available yet."
      countLabel="projects"
    />
  );
};
