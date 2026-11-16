import type {ProjectTableRow} from '@/features/projects/api';

export const makeProjectTableRow = (overrides: Partial<ProjectTableRow>): ProjectTableRow => ({
  id: 'project-1',
  semester_label: '2024-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Solar Team',
  project_title: 'Solar Project',
  organization: 'Solar Org',
  industry: 'Energy',
  abstract: 'A solar project abstract.',
  student_names: 'Alex Student',
  track: null,
  presentation_order: null,
  ...overrides,
});
