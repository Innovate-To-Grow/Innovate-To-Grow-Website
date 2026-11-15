import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

export const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Alpha Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

export const alphaRow = makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'});
export const bravoRow = makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'});
export const charlieRow = makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'});
