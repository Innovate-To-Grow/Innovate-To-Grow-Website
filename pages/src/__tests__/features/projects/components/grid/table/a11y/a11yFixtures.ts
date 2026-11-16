import {vi} from 'vitest';

import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridRow,
  type ProjectGridSortDirection,
} from '@/features/projects/components/grid/contracts/projectGrid';

export const makeRows = (count: number, overrides: Partial<ProjectGridRow> = {}): ProjectGridItem[] =>
  createProjectGridItems(
    Array.from(
      {length: count},
      (_, index): ProjectGridRow => ({
        id: `a11y-${index}`,
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
        ...overrides,
      }),
    ),
    'a11y',
  );

export const rows = makeRows(2);

export const baseProps = {
  columns: PAST_PROJECT_GRID_COLUMNS,
  rows,
  pagedRows: rows,
  filteredCount: 2,
  totalCount: 2,
  search: '',
  sortField: 'semester_label' as ProjectGridColumnKey,
  sortDirection: 'asc' as ProjectGridSortDirection,
  onSearchChange: vi.fn(),
  onSortChange: vi.fn(),
  expandedKeys: new Set<string>(),
  onToggleExpanded: vi.fn(),
  onToggleAllDetails: vi.fn(),
  page: 0,
  totalPages: 1,
  onPageChange: vi.fn(),
  pageSize: 10,
  pageSizeOptions: [10, 25],
  onPageSizeChange: vi.fn(),
};

export const sortOptions = [{field: 'project_title' as ProjectGridColumnKey, label: 'Project title'}];

/** The server is still searching abstracts; then it answers, adding the rows `addedRowsKey` names. */
export const asking = {pending: true, addedRowsKey: null, tooBroad: false, failed: false};
export const answered = (addedRowsKey: string) => ({pending: false, addedRowsKey, tooBroad: false, failed: false});
