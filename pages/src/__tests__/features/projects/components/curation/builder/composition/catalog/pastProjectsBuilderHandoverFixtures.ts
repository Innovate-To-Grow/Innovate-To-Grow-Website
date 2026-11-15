import {fireEvent, screen} from '@testing-library/react';

import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

export const ID_ALPHA = '11111111-1111-4111-8111-111111111111';
export const ID_BRAVO = '22222222-2222-4222-8222-222222222222';
export const ID_GONE = '33333333-3333-4333-8333-333333333333';

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
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

// Compact archive rows, as the archive endpoint returns them: details load when they are added.
export const ROWS: ProjectGridRow[] = [
  makeRow({id: ID_ALPHA, team_number: 'T01', project_title: 'Alpha Project'}),
  makeRow({id: ID_BRAVO, team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
];

export const DRAFT_STORAGE_KEY = 'past-projects:builder:draft';
export const signedOut = {isAuthenticated: false, isInitializing: false, unverified: false, user: null};

export const draftSection = () => screen.getByRole('heading', {level: 2, name: /curation draft/i}).closest('section') as HTMLElement;

/** Checks the rows and adds them; their details load first, so the draft card shows a moment later. */
export const addToCuration = async (...titles: string[]) => {
  for (const title of titles) {
    fireEvent.click(screen.getAllByLabelText(`Select ${title}`)[0]);
  }
  fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
  await screen.findByRole('heading', {level: 2, name: /curation draft/i});
};
