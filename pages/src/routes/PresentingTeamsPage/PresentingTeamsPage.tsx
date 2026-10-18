import {useMemo} from 'react';
import {CurrentProjectsView} from '@/features/projects/components/CurrentProjectsView';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

export const PresentingTeamsPage = () => {
  const {rows, loading, error, classLabels} = useCurrentProjectGridData();
  const presentingRows = useMemo(() => rows.filter((row) => row.is_presenting === 'Yes'), [rows]);

  return (
    <CurrentProjectsView
      title="Presenting Teams"
      lede="Teams presenting at this semester's Innovate to Grow showcase. Search by team, class or organization, and open a project to read its abstract and team members."
      rows={presentingRows}
      loading={loading}
      error={error}
      classLabels={classLabels}
      namespace="presenting-teams"
      emptyMessage="No presenting teams are available yet."
      countLabel="teams"
    />
  );
};
