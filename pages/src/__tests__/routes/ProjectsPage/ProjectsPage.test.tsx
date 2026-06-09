import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {ProjectsPage} from '@/routes/ProjectsPage/ProjectsPage';
import type {ProjectGridItem, ProjectGridRow} from '@/features/projects';

const projectsPageMocks = vi.hoisted(() => ({
  currentData: {
    rows: [] as ProjectGridRow[],
    loading: false,
    error: null as string | null,
  },
  tableArgs: null as unknown,
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
  useCurrentProjectGridData: () => projectsPageMocks.currentData,
}));

vi.mock('@/features/projects', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects')>('@/features/projects');
  return {
    ...actual,
    ProjectGridTable: ({rows, emptyMessage, countLabel, loading, error}: {
      rows: ProjectGridItem[];
      emptyMessage: string;
      countLabel: string;
      loading?: boolean;
      error?: string | null;
    }) => (
      <div data-testid="project-grid-table">
        {loading ? 'loading' : null}
        {error ? `error:${error}` : null}
        {emptyMessage}
        {countLabel}:{rows.length}
      </div>
    ),
    useProjectGridTable: (args: unknown) => {
      projectsPageMocks.tableArgs = args;
      const rows = (args as {rows: ProjectGridItem[]}).rows;
      return {
        allDetailsExpanded: false,
        expandedKeys: new Set<string>(),
        filteredRows: rows,
        page: 0,
        pageSize: 25,
        pageSizeOptions: [10, 25],
        pagedRows: rows,
        search: (args as {initialSearch?: string}).initialSearch ?? '',
        setPage: vi.fn(),
        setPageSize: vi.fn(),
        setSearch: vi.fn(),
        sortDirection: 'asc',
        sortField: 'class_code',
        toggleAllDetails: vi.fn(),
        toggleExpanded: vi.fn(),
        toggleSort: vi.fn(),
        totalPages: 1,
      };
    },
  };
});

const row = (is_presenting = 'Yes'): ProjectGridRow => ({
  semester_label: '2026 Spring',
  class_code: 'CSE',
  team_number: '101',
  team_name: 'Team One',
  project_title: 'Project One',
  organization: 'UC Merced',
  industry: 'Education',
  abstract: '',
  student_names: '',
  is_presenting,
});

describe('ProjectsPage', () => {
  beforeEach(() => {
    projectsPageMocks.currentData = {
      rows: [row()],
      loading: false,
      error: null,
    };
    projectsPageMocks.tableArgs = null;
  });

  it('renders current projects and passes URL search into table state', () => {
    render(<MemoryRouter initialEntries={['/current-projects?value=robot']}><ProjectsPage /></MemoryRouter>);

    expect(screen.getByRole('heading', {name: 'Current Projects'})).toBeInTheDocument();
    expect(screen.getByTestId('project-grid-table')).toHaveTextContent('projects:1');
    expect(projectsPageMocks.tableArgs).toMatchObject({
      defaultSortField: 'class_code',
      defaultSortDirection: 'asc',
      initialSearch: 'robot',
    });
  });
});
