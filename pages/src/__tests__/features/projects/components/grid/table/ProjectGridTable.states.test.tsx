import {useState} from 'react';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {useProjectGridTable} from '@/features/projects/components/grid/state/useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridRow,
  type ProjectGridSortDirection,
} from '@/features/projects/components/grid/contracts/projectGrid';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';

// The grid's empty, loading and failure states, its count line, and a row's copy feedback.

const {fetchDetail} = vi.hoisted(() => ({fetchDetail: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: fetchDetail,
}));

// Each test uses its own ids: loaded (or failed) details are kept per project between renders.
const makeRows = (prefix: string, count: number, overrides: Partial<ProjectGridRow> = {}): ProjectGridItem[] =>
  createProjectGridItems(
    Array.from(
      {length: count},
      (_, index): ProjectGridRow => ({
        id: `${prefix}-${index}`,
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
    prefix,
  );

const rows = makeRows('states', 2);

const baseProps = {
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
  page: 0,
  totalPages: 1,
  onPageChange: vi.fn(),
  pageSize: 10,
  pageSizeOptions: [10, 25],
  onPageSizeChange: vi.fn(),
};

const noRows = {rows: [], pagedRows: [], filteredCount: 0, totalCount: 0};

const emptyState = {
  emptyTitle: 'No current projects yet',
  emptyMessage: "This semester's projects appear here once the schedule is published.",
  emptyActions: (
    <a className="itg-btn itg-btn-outline" href="/past-projects">
      Search Past Projects
    </a>
  ),
};

/** A past-projects table of one row, opened from its Details button so the row reports its own state. */
const OneRowGrid = ({row}: {row: ProjectGridItem}) => {
  const [items] = useState([row]);
  const table = useProjectGridTable({rows: items, defaultSortField: 'semester_label'});
  return (
    <MemoryRouter>
      <ProjectGridTable
        {...baseProps}
        rows={items}
        pagedRows={table.pagedRows}
        filteredCount={1}
        totalCount={1}
        linkScope="past"
        loadMissingDetails
        expandedKeys={table.expandedKeys}
        onToggleExpanded={table.toggleExpanded}
      />
    </MemoryRouter>
  );
};

const openRow = (row: ProjectGridItem) => {
  render(<OneRowGrid row={row} />);
  fireEvent.click(screen.getByRole('button', {name: `Details for ${row.project_title}`}));
};

describe('ProjectGridTable states', () => {
  afterEach(() => {
    cleanup();
    fetchDetail.mockReset();
    vi.unstubAllGlobals();
    Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
  });

  it('shows an empty schedule as a heading, its text and one action, like the no-results state', () => {
    const {container} = render(<ProjectGridTable {...baseProps} {...noRows} {...emptyState} />);

    const heading = screen.getByRole('heading', {level: 2, name: 'No current projects yet'});
    const state = heading.closest('.itg-empty-state') as HTMLElement;
    expect(state).toHaveClass('project-grid-empty-state');
    expect(within(state).getByText(emptyState.emptyMessage)).toHaveClass('itg-empty-state-text');
    expect(within(state).getByRole('link', {name: 'Search Past Projects'})).toHaveClass('itg-btn-outline');
    expect(container.querySelector('.project-grid-empty')).toBeNull();
    expect(container.querySelector('.project-grid-count')).toBeNull();
  });

  it('heads the empty state at the no-results level, and keeps the plain message without a title', () => {
    const {container, rerender} = render(
      <ProjectGridTable {...baseProps} {...noRows} {...emptyState} noResultsHeadingLevel={3} />,
    );
    expect(screen.getByRole('heading', {level: 3, name: 'No current projects yet'})).toBeInTheDocument();

    rerender(<ProjectGridTable {...baseProps} {...noRows} emptyMessage="No projects in this table." />);
    expect(screen.queryByRole('heading')).toBeNull();
    expect(container.querySelector('p.project-grid-empty')).toHaveTextContent('No projects in this table.');
  });

  it('focuses the empty state heading when Try Again brings back no rows', () => {
    stubGridLayout('desktop');
    const onRetry = vi.fn();
    const {rerender} = render(<ProjectGridTable {...baseProps} error="We couldn't load the projects." onRetry={onRetry} />);

    const tryAgain = screen.getByRole('button', {name: 'Try Again'});
    tryAgain.focus();
    fireEvent.click(tryAgain);
    rerender(<ProjectGridTable {...baseProps} loading onRetry={onRetry} />);
    rerender(<ProjectGridTable {...baseProps} {...noRows} {...emptyState} onRetry={onRetry} />);

    expect(document.activeElement).toBe(screen.getByRole('heading', {level: 2, name: 'No current projects yet'}));
  });

  it('keeps "· showing a–b" in a span of its own, with the line reading as before', () => {
    const {container, rerender} = render(<ProjectGridTable {...baseProps} />);
    const count = () => container.querySelector('.project-grid-count') as HTMLElement;

    expect(count().textContent).toBe('2 projects · showing 1–2');
    expect(count().querySelector('.project-grid-count-range')).toHaveTextContent(/^· showing 1–2$/);

    rerender(<ProjectGridTable {...baseProps} search="project 1" pagedRows={rows.slice(0, 1)} filteredCount={1} />);
    expect(count().textContent).toBe('1 of 2 projects matches “project 1” · showing 1–1');
    expect(count().querySelector('.project-grid-count-range')).toHaveTextContent(/^· showing 1–1$/);
  });

  it('shows the loading indicator while a row loads its details, then an outline Try Again if they fail', async () => {
    stubGridLayout('desktop');
    let fail: (error: Error) => void = () => undefined;
    fetchDetail.mockImplementation(() => new Promise((_resolve, reject) => (fail = reject)));
    const [row] = makeRows('states-fail', 1, {abstract: '', student_names: ''});
    openRow(row);

    const loading = screen.getByRole('status');
    expect(loading).toHaveTextContent('Loading project details…');
    expect(loading.querySelector('.loading-indicator-spinner')).toBeInTheDocument();

    fail(new Error('boom'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load project details.');
    // Named after its project, like the row's other controls; outline, so it does not outrank the page's actions.
    const tryAgain = screen.getByRole('button', {name: 'Try Again for Project 1'});
    expect(tryAgain).toHaveClass('itg-btn', 'itg-btn-outline');
    expect(tryAgain.closest('.project-grid-detail-error')).toBeInTheDocument();

    fetchDetail.mockResolvedValue({...row, abstract: 'Loaded abstract.', student_names: 'Ada'});
    fireEvent.click(tryAgain);
    expect(await screen.findByText('Loaded abstract.')).toBeInTheDocument();
  });

  it.each([
    ['success', () => Promise.resolve(), 'Project link copied.', 'itg-success'],
    ['error', () => Promise.reject(new Error('denied')), 'Could not copy the link.', 'itg-error'],
  ])('colours the copy status by how the copy went (%s)', async (_case, writeText, message, toneClass) => {
    stubGridLayout('desktop');
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    const [row] = makeRows(`states-copy-${toneClass}`, 1);
    openRow(row);

    fireEvent.click(screen.getByRole('button', {name: 'Copy Project Link for Project 1'}));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(message);
    expect(status).toHaveClass('project-grid-copy-status', toneClass);
  });
});
