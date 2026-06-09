import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {PresentingTeamsPage} from '@/routes/PresentingTeamsPage/PresentingTeamsPage';
import type {ProjectGridItem, ProjectGridRow} from '@/features/projects';

const presentingMocks = vi.hoisted(() => ({
  currentData: {
    rows: [] as ProjectGridRow[],
    loading: false,
    error: null as string | null,
  },
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
  useCurrentProjectGridData: () => presentingMocks.currentData,
}));

vi.mock('@/features/projects', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects')>('@/features/projects');
  return {
    ...actual,
    ProjectGridTable: ({rows, emptyMessage, countLabel}: {rows: ProjectGridItem[]; emptyMessage: string; countLabel: string}) => (
      <div data-testid="presenting-grid">{emptyMessage} {countLabel}:{rows.length}</div>
    ),
    useProjectGridTable: (args: {rows: ProjectGridItem[]; initialSearch?: string}) => ({
      allDetailsExpanded: false,
      expandedKeys: new Set<string>(),
      filteredRows: args.rows,
      page: 0,
      pageSize: 25,
      pageSizeOptions: [10, 25],
      pagedRows: args.rows,
      search: args.initialSearch ?? '',
      setPage: vi.fn(),
      setPageSize: vi.fn(),
      setSearch: vi.fn(),
      sortDirection: 'asc',
      sortField: 'class_code',
      toggleAllDetails: vi.fn(),
      toggleExpanded: vi.fn(),
      toggleSort: vi.fn(),
      totalPages: 1,
    }),
  };
});

const row = (is_presenting: string): ProjectGridRow => ({
  semester_label: '2026 Spring',
  class_code: 'CSE',
  team_number: is_presenting === 'Yes' ? '101' : '102',
  team_name: 'Team',
  project_title: 'Project',
  organization: 'UC Merced',
  industry: 'Education',
  abstract: '',
  student_names: '',
  is_presenting,
});

describe('PresentingTeamsPage', () => {
  beforeEach(() => {
    presentingMocks.currentData = {
      rows: [row('Yes'), row('No')],
      loading: false,
      error: null,
    };
  });

  it('renders only presenting teams', () => {
    render(<MemoryRouter><PresentingTeamsPage /></MemoryRouter>);

    expect(screen.getByRole('heading', {name: 'Presenting Teams'})).toBeInTheDocument();
    expect(screen.getByTestId('presenting-grid')).toHaveTextContent('teams:1');
  });
});
