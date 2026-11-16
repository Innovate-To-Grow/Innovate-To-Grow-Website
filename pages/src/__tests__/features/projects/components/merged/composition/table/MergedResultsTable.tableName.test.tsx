import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// The saved list's table and its pager are named after the list's heading, like the search tables beside it.

vi.mock('@/features/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth')>()),
  useAuth: () => ({isAuthenticated: false, user: null}),
}));

const items = createProjectGridItems(
  Array.from(
    {length: 12},
    (_, index): ProjectGridRow => ({
      semester_label: '2025-1 Spring',
      class_code: 'CAP',
      team_number: `${index + 1}`,
      team_name: `Team ${index + 1}`,
      project_title: `Project ${index + 1}`,
      organization: 'Acme',
      industry: 'Energy',
      abstract: 'An abstract',
      student_names: 'Ada',
      is_presenting: '',
    }),
  ),
  'names',
);

describe('MergedResultsTable table name', () => {
  afterEach(() => cleanup());

  it("names the builder's table and pager after the list's title", () => {
    render(<MergedResultsTable rows={items} title="Saved Merged Results" />);

    expect(screen.getByRole('table', {name: 'Saved Merged Results'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Saved Merged Results pages'})).toBeInTheDocument();
  });

  it("names a shared curation's table and pager after the curation", () => {
    render(<MergedResultsTable rows={items} sharedMode title="Spring picks" />);

    expect(screen.getByRole('table', {name: 'Spring picks'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Spring picks pages'})).toBeInTheDocument();
  });
});
