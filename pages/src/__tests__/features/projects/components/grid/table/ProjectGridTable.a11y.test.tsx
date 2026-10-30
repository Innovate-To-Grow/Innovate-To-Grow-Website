import {useState} from 'react';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

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

// What a screen reader or keyboard user meets in the grid: names that say which project a control belongs to,
// focus that stays on the page, one message for View All Details, and no controls for rows that are not there.

const {fetchDetail} = vi.hoisted(() => ({fetchDetail: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: fetchDetail,
}));

const makeRows = (count: number, overrides: Partial<ProjectGridRow> = {}): ProjectGridItem[] =>
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

const rows = makeRows(2);

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
  onToggleAllDetails: vi.fn(),
  page: 0,
  totalPages: 1,
  onPageChange: vi.fn(),
  pageSize: 10,
  pageSizeOptions: [10, 25],
  onPageSizeChange: vi.fn(),
};

const sortOptions = [{field: 'project_title' as ProjectGridColumnKey, label: 'Project title'}];

/** The server is still searching abstracts; then it answers, adding the rows `addedRowsKey` names. */
const asking = {pending: true, addedRowsKey: null, tooBroad: false};
const answered = (addedRowsKey: string) => ({pending: false, addedRowsKey, tooBroad: false});

/** A past-projects table whose rows have no details yet, so opening one loads them (and stays loading). */
const LoadingGrid = () => {
  const [items] = useState(() => makeRows(3, {abstract: '', student_names: ''}));
  const table = useProjectGridTable({rows: items, defaultSortField: 'semester_label'});
  return (
    <ProjectGridTable
      {...baseProps}
      loadMissingDetails
      linkScope="past"
      rows={items}
      pagedRows={table.pagedRows}
      filteredCount={items.length}
      totalCount={items.length}
      expandedKeys={table.expandedKeys}
      onToggleExpanded={table.toggleExpanded}
      onToggleAllDetails={table.toggleAllDetails}
      allDetailsExpanded={table.allDetailsExpanded}
    />
  );
};

describe('ProjectGridTable accessibility', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchDetail.mockReset();
  });

  it('names each row control after its project, with one name whether open or closed', () => {
    stubGridLayout('desktop');
    const pastRows = makeRows(2);
    const {container} = render(
      <ProjectGridTable {...baseProps} linkScope="past" expandedKeys={new Set([pastRows[0].__key])} rows={pastRows} pagedRows={pastRows} />,
    );
    const table = within(container.querySelector('.project-grid-table-wrap') as HTMLElement);

    // Before: every toggle was "Details", or "Hide" once open, and every link "Open the project page".
    expect(table.getByRole('button', {name: 'Details for Project 1'})).toHaveAttribute('aria-expanded', 'true');
    expect(table.getByRole('button', {name: 'Details for Project 2'})).toHaveAttribute('aria-expanded', 'false');
    expect(table.queryByRole('button', {name: 'Hide'})).toBeNull();
    expect(table.getByRole('group', {name: 'Details for Project 1'})).toHaveTextContent('An abstract');
    expect(table.getByRole('link', {name: 'Open the project page for Project 1 (opens in a new tab)'})).toBeInTheDocument();
    expect(table.getByRole('button', {name: 'Copy project link for Project 1'})).toBeInTheDocument();
  });

  it('names the phone toggle after its project too', () => {
    stubGridLayout('phone');
    render(<ProjectGridTable {...baseProps} expandedKeys={new Set([rows[1].__key])} />);

    expect(screen.getByRole('button', {name: 'Show details for Project 1'})).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', {name: 'Hide details for Project 2'})).toHaveAttribute('aria-expanded', 'true');
  });

  it('reads the Details heading of a list with Remove buttons as one phrase', () => {
    stubGridLayout('desktop');
    render(<ProjectGridTable {...baseProps} onDeleteRow={vi.fn()} />);

    expect(screen.getByRole('columnheader', {name: 'Details and removal'})).toBeInTheDocument();
  });

  it('names the table and its pager when given a label', () => {
    stubGridLayout('desktop');
    render(<ProjectGridTable {...baseProps} totalPages={3} tableLabel="Search Table 2" />);

    expect(screen.getByRole('table', {name: 'Search Table 2'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Search Table 2 pages'})).toBeInTheDocument();
  });

  it('keeps focus on the search field when Clear search takes the no-results message away', () => {
    const onSearchChange = vi.fn();
    const onClearFilters = vi.fn();
    render(
      <ProjectGridTable
        {...baseProps}
        search="zzz"
        filteredCount={0}
        pagedRows={[]}
        onSearchChange={onSearchChange}
        onClearFilters={onClearFilters}
      />,
    );

    const clear = screen.getByRole('button', {name: 'Clear search'});
    clear.focus();
    fireEvent.click(clear);

    expect(document.activeElement).toBe(screen.getByRole('searchbox', {name: 'Search'}));
    expect(onSearchChange).toHaveBeenCalledWith('');
    expect(onClearFilters).toHaveBeenCalled();
  });

  it('moves focus to the count line when another control replaces the search field', () => {
    const {container} = render(
      <ProjectGridTable
        {...baseProps}
        search="zzz"
        filteredCount={0}
        pagedRows={[]}
        searchControl={<form aria-label="AI search" />}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Clear search'}));
    expect(document.activeElement).toBe(container.querySelector('.project-grid-count'));
  });

  it("keeps focus in the grid when the server's matches take the no-results message away", () => {
    stubGridLayout('desktop');
    const {container, rerender} = render(
      <ProjectGridTable {...baseProps} search="EnergyPro" serverSearch={asking} filteredCount={0} pagedRows={[]} />,
    );
    expect(screen.getByText('Still searching project abstracts…')).toBeInTheDocument();
    screen.getByRole('button', {name: 'Clear search'}).focus();

    // The server finds a project by its abstract: rows replace the message, and its Clear button with it.
    rerender(
      <ProjectGridTable
        {...baseProps}
        search="EnergyPro"
        serverSearch={answered('a11y-1')}
        filteredCount={1}
        pagedRows={[rows[1]]}
      />,
    );
    expect(screen.queryByRole('button', {name: 'Clear search'})).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('.project-grid-count'));
    expect(document.activeElement).toHaveTextContent('1 of 2 projects matches “EnergyPro”');
  });

  it('leaves focus where the visitor moved it before the answer took the no-results message away', () => {
    stubGridLayout('desktop');
    const {rerender} = render(
      <ProjectGridTable {...baseProps} search="EnergyPro" serverSearch={asking} filteredCount={0} pagedRows={[]} />,
    );
    const clear = screen.getByRole('button', {name: 'Clear search'});
    clear.focus();
    // The visitor clicks blank page space: focus leaves Clear search, which is still there.
    clear.blur();

    rerender(
      <ProjectGridTable
        {...baseProps}
        search="EnergyPro"
        serverSearch={answered('a11y-1')}
        filteredCount={1}
        pagedRows={[rows[1]]}
      />,
    );
    expect(document.activeElement).toBe(document.body);
  });

  describe("when the server's answer sorts rows in above the focused row", () => {
    // "water" first finds Projects 1 and 2 by their own text, two to a page. The server then finds Projects 3 and 4
    // by their abstracts, and they sort in above Project 2, which moves to page 2.
    const fourRows = makeRows(4);
    const searchProps = {...baseProps, rows: fourRows, filteredCount: 4, totalCount: 4, totalPages: 2, search: 'water'};
    const firstPage = fourRows.slice(0, 2);
    const answeredPage = [fourRows[2], fourRows[0]];

    it.each(['desktop', 'phone'] as const)('moves focus from a row that left the page to the count line (%s)', (layout) => {
      stubGridLayout(layout);
      const {container, rerender} = render(
        <ProjectGridTable {...searchProps} serverSearch={asking} pagedRows={firstPage} />,
      );
      screen.getByRole('button', {name: /details for Project 2$/i}).focus();
      const count = container.querySelector('.project-grid-count') as HTMLElement;
      const focusCount = vi.spyOn(count, 'focus');

      rerender(<ProjectGridTable {...searchProps} serverSearch={answered('a11y-2 a11y-3')} pagedRows={answeredPage} />);
      expect(screen.queryByRole('button', {name: /details for Project 2$/i})).toBeNull();
      expect(document.activeElement).toBe(count);
      // The browser does not scroll to it on its own; the grid scrolls only when the line is out of view.
      expect(focusCount).toHaveBeenCalledWith({preventScroll: true});
    });

    it('scrolls the count line into view only when it is off-screen', () => {
      stubGridLayout('desktop');
      const scrollIntoView = vi.fn();
      Element.prototype.scrollIntoView = scrollIntoView;
      const {container, rerender} = render(
        <ProjectGridTable {...searchProps} serverSearch={asking} pagedRows={firstPage} />,
      );
      // The visitor scrolled down to the last row: the count line is far above the viewport.
      const count = container.querySelector('.project-grid-count') as HTMLElement;
      vi.spyOn(count, 'getBoundingClientRect').mockReturnValue({top: -900} as DOMRect);
      screen.getByRole('button', {name: 'Details for Project 2'}).focus();

      rerender(<ProjectGridTable {...searchProps} serverSearch={answered('a11y-2 a11y-3')} pagedRows={answeredPage} />);
      expect(document.activeElement).toBe(count);
      expect(scrollIntoView).toHaveBeenCalledWith({block: 'start'});
      Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
    });

    it('leaves focus alone when the row is still on the page', () => {
      stubGridLayout('desktop');
      const {rerender} = render(<ProjectGridTable {...searchProps} serverSearch={asking} pagedRows={firstPage} />);
      const details = screen.getByRole('button', {name: 'Details for Project 1'});
      details.focus();

      rerender(<ProjectGridTable {...searchProps} serverSearch={answered('a11y-2 a11y-3')} pagedRows={answeredPage} />);
      expect(document.activeElement).toBe(details);
    });

    it("leaves a row the visitor's own change took away to the table's owner", () => {
      stubGridLayout('desktop');
      const {rerender} = render(
        <ProjectGridTable {...searchProps} serverSearch={answered('a11y-2 a11y-3')} pagedRows={answeredPage} />,
      );
      screen.getByRole('button', {name: 'Details for Project 3'}).focus();

      // Remove from Table: the row leaves, with no new answer from the server (the same rows, asked again).
      rerender(
        <ProjectGridTable {...searchProps} serverSearch={answered('a11y-2 a11y-3')} pagedRows={[fourRows[0], fourRows[1]]} />,
      );
      expect(document.activeElement).toBe(document.body);
    });
  });

  it('keeps focus in the grid when the table goes back to its first page under the pager', () => {
    stubGridLayout('desktop');
    const {container, rerender} = render(<ProjectGridTable {...baseProps} page={2} totalPages={3} />);
    screen.getByRole('button', {name: 'Previous'}).focus();

    // The server's answer started the search over on page 1: Previous is disabled under the visitor.
    rerender(<ProjectGridTable {...baseProps} page={0} totalPages={3} />);
    expect(screen.getByRole('button', {name: 'Previous'})).toBeDisabled();
    expect(document.activeElement).toBe(container.querySelector('.project-grid-count'));
  });

  it('leaves focus alone when a control outside the results goes away', () => {
    stubGridLayout('desktop');
    const merge = <button type="button">Merge</button>;
    const {rerender} = render(
      <ProjectGridTable {...baseProps} search="zzz" filteredCount={0} pagedRows={[]} toolbar={merge} />,
    );
    screen.getByRole('button', {name: 'Merge'}).focus();

    rerender(<ProjectGridTable {...baseProps} search="zzz" filteredCount={0} pagedRows={[]} />);
    expect(document.activeElement).toBe(document.body);
  });

  it('with no rows matching, keeps the count but not the controls that act on rows', () => {
    const {container, rerender} = render(
      <ProjectGridTable {...baseProps} sortOptions={sortOptions} search="zzz" filteredCount={0} pagedRows={[]} />,
    );

    const resultsBar = container.querySelector('.project-grid-results-bar') as HTMLElement;
    expect(resultsBar).toHaveTextContent('0 of 2 projects match “zzz”');
    expect(within(resultsBar).queryByLabelText('Sort by')).toBeNull();
    expect(within(resultsBar).queryByLabelText('Per page')).toBeNull();
    expect(screen.queryByRole('button', {name: 'View All Details'})).toBeNull();

    // Without a Sort select the toggle sits in the filter well, which stays: there it is disabled.
    rerender(<ProjectGridTable {...baseProps} search="zzz" filteredCount={0} pagedRows={[]} />);
    expect(screen.getByRole('button', {name: 'View All Details'})).toBeDisabled();
    rerender(<ProjectGridTable {...baseProps} />);
    expect(screen.getByRole('button', {name: 'View All Details'})).toBeEnabled();
  });

  it('says once that View All Details opened every row, instead of each row saying it is loading', () => {
    stubGridLayout('desktop');
    fetchDetail.mockImplementation(
      (_id: string, signal: AbortSignal) =>
        new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')))),
    );
    const {container} = render(<LoadingGrid />);
    const message = container.querySelector('.project-grid-table-shell > p[aria-live="polite"]') as HTMLElement;
    expect(message).toHaveTextContent('');

    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(screen.getAllByText('Loading project details...')).toHaveLength(3);
    expect(screen.queryAllByRole('status')).toHaveLength(0);
    expect(message).toHaveTextContent('All details shown.');

    fireEvent.click(screen.getByRole('button', {name: 'Hide All Details'}));
    expect(message).toHaveTextContent('All details hidden.');

    // A row opened by its own button still says it is loading.
    fireEvent.click(screen.getByRole('button', {name: 'Details for Project 1'}));
    expect(screen.getByRole('status')).toHaveTextContent('Loading project details...');
  });

  it('says it is loading the rows', () => {
    render(<ProjectGridTable {...baseProps} loading />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading project data...');
  });

  it('still announces the first row opened when it is the only row', () => {
    stubGridLayout('desktop');
    fetchDetail.mockImplementation(
      (_id: string, signal: AbortSignal) =>
        new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')))),
    );
    const Single = () => {
      const [items] = useState(() => makeRows(1, {id: 'a11y-single', abstract: '', student_names: ''}));
      const table = useProjectGridTable({rows: items, defaultSortField: 'semester_label'});
      return (
        <ProjectGridTable
          {...baseProps}
          loadMissingDetails
          rows={items}
          pagedRows={table.pagedRows}
          filteredCount={1}
          totalCount={1}
          expandedKeys={table.expandedKeys}
          onToggleExpanded={table.toggleExpanded}
          allDetailsExpanded={table.allDetailsExpanded}
        />
      );
    };
    render(<Single />);

    // Opening the only row also makes "every row open"; it was still opened on its own, so it reports itself.
    act(() => fireEvent.click(screen.getByRole('button', {name: 'Details for Project 1'})));
    expect(screen.getByRole('status')).toHaveTextContent('Loading project details...');
  });

  describe('Try again', () => {
    const LOAD_ERROR = "We couldn't load the projects. Please try again.";
    const onRetry = vi.fn();
    const failed = <ProjectGridTable {...baseProps} error={LOAD_ERROR} onRetry={onRetry} />;
    const reloading = <ProjectGridTable {...baseProps} loading onRetry={onRetry} />;

    beforeEach(() => onRetry.mockClear());

    /** Presses Try again as a keyboard user does: the button has focus first. */
    const pressTryAgain = () => {
      const button = screen.getByRole('button', {name: 'Try again'});
      button.focus();
      fireEvent.click(button);
    };

    it('keeps focus in the grid: on the loading line, then on the count line once the rows are back', () => {
      stubGridLayout('desktop');
      const {rerender} = render(failed);

      pressTryAgain();
      expect(onRetry).toHaveBeenCalledTimes(1);
      // The button left with the error; focus went to the loading line, not to the page.
      rerender(reloading);
      expect(document.activeElement).toBe(screen.getByRole('status'));

      rerender(<ProjectGridTable {...baseProps} onRetry={onRetry} />);
      expect(document.activeElement).toHaveClass('project-grid-count');
      expect(document.activeElement).toHaveTextContent('2 projects');
    });

    it('returns focus to Try again when the load fails again, and to the empty message when no rows come back', () => {
      stubGridLayout('desktop');
      const {rerender} = render(failed);

      pressTryAgain();
      rerender(reloading);
      rerender(failed);
      expect(document.activeElement).toBe(screen.getByRole('button', {name: 'Try again'}));

      pressTryAgain();
      rerender(reloading);
      rerender(
        <ProjectGridTable
          {...baseProps}
          rows={[]}
          pagedRows={[]}
          filteredCount={0}
          totalCount={0}
          emptyMessage="No current projects are available yet."
          onRetry={onRetry}
        />,
      );
      expect(document.activeElement).toHaveTextContent('No current projects are available yet.');
    });

    it('leaves focus where the visitor moved it while the rows loaded', () => {
      stubGridLayout('desktop');
      const {rerender} = render(failed);

      pressTryAgain();
      rerender(reloading);
      const search = screen.getByRole('searchbox');
      search.focus();
      rerender(<ProjectGridTable {...baseProps} onRetry={onRetry} />);
      expect(document.activeElement).toBe(search);
    });

    it('does not move focus when the rows load without a retry', () => {
      stubGridLayout('desktop');
      const {rerender} = render(reloading);
      rerender(<ProjectGridTable {...baseProps} onRetry={onRetry} />);
      expect(document.activeElement).toBe(document.body);
    });
  });
});
