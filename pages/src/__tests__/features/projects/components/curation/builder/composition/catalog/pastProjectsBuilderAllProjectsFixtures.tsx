import {fireEvent, screen} from '@testing-library/react';
import type {ReactElement} from 'react';

import type {ProjectTableRow} from '@/features/projects/api';
import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

export const ID_CURRENT = '11111111-1111-4111-8111-111111111111';
export const ID_ARCHIVE = '22222222-2222-4222-8222-222222222222';
export const ID_GONE = '33333333-3333-4333-8333-333333333333';

export const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Alpha Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

// A current-semester row, as /projects/all/ lists it first, then an archive row.
export const ROWS: ProjectGridRow[] = [
  makeRow({id: ID_CURRENT, semester_label: '2026 Fall', catalog: 'current', is_presenting: 'Yes'}),
  makeRow({id: ID_ARCHIVE, team_number: '102', project_title: 'Bravo Project', catalog: 'archive'}),
];

export const RAW_ERROR = 'Request failed with status code 503';
export const signedOut = {isAuthenticated: false, isInitializing: false, unverified: false, user: null};
export const signedIn = {
  isAuthenticated: true,
  isInitializing: false,
  unverified: false,
  user: {member_uuid: 'member-1', email: 'member@example.com'},
};

export const inAllProjects = (ui: ReactElement) => (
  <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>{ui}</ProjectCatalogContext.Provider>
);

export interface BuilderProps {
  rows?: ProjectGridRow[];
  loading?: boolean;
  error?: string | null;
  onRefreshRows?: () => void;
}

export const searchTable = (name: string) => screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;
export const draftSection = () =>
  screen.getByRole('heading', {level: 2, name: /curation draft/i}).closest('section') as HTMLElement;

/** Checks the rows and adds them; their details load first, so the draft card shows a moment later. */
export const addToCuration = async (...titles: string[]) => {
  for (const title of titles) {
    fireEvent.click(screen.getAllByLabelText(`Select ${title}`)[0]);
  }
  fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
  await screen.findByRole('heading', {level: 2, name: /curation draft/i});
};

export const aiResult = (overrides: Partial<ProjectTableRow>): ProjectTableRow => ({
  id: ID_CURRENT,
  semester_label: '2026 Fall',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Irrigation Sensor',
  organization: 'Acme',
  industry: 'Agriculture',
  abstract: 'Abstract-101',
  student_names: 'Ada Lovelace',
  track: 1,
  presentation_order: 1,
  ...overrides,
});
