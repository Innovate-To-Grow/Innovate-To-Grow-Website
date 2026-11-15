import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {answered, asking, baseProps, makeRows, rows} from '@/__tests__/features/projects/components/grid/table/a11y/a11yFixtures';

// What a screen reader or keyboard user meets in the grid: names that say which project a control belongs to,
// focus that stays on the page, one message for View All Details, and no controls for rows that are not there.

const {fetchDetail} = vi.hoisted(() => ({fetchDetail: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: fetchDetail,
}));

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
    expect(table.getByRole('link', {name: 'Open the Project Page for Project 1 (opens in a new tab)'})).toBeInTheDocument();
    expect(table.getByRole('button', {name: 'Copy Project Link for Project 1'})).toBeInTheDocument();
  });

  it('names the phone toggle after its project too', () => {
    stubGridLayout('phone');
    render(<ProjectGridTable {...baseProps} expandedKeys={new Set([rows[1].__key])} />);

    expect(screen.getByRole('button', {name: 'Show Details for Project 1'})).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', {name: 'Hide Details for Project 2'})).toHaveAttribute('aria-expanded', 'true');
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

  it('keeps focus on the search field when Clear Search takes the no-results message away', () => {
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

    const clear = screen.getByRole('button', {name: 'Clear Search'});
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

    fireEvent.click(screen.getByRole('button', {name: 'Clear Search'}));
    expect(document.activeElement).toBe(container.querySelector('.project-grid-count'));
  });

  it("keeps focus in the grid when the server's matches take the no-results message away", () => {
    stubGridLayout('desktop');
    const {container, rerender} = render(
      <ProjectGridTable {...baseProps} search="EnergyPro" serverSearch={asking} filteredCount={0} pagedRows={[]} />,
    );
    expect(screen.getByText('Still searching project abstracts…')).toBeInTheDocument();
    screen.getByRole('button', {name: 'Clear Search'}).focus();

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
    expect(screen.queryByRole('button', {name: 'Clear Search'})).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('.project-grid-count'));
    expect(document.activeElement).toHaveTextContent('1 of 2 projects matches “EnergyPro”');
  });

  it('leaves focus where the visitor moved it before the answer took the no-results message away', () => {
    stubGridLayout('desktop');
    const {rerender} = render(
      <ProjectGridTable {...baseProps} search="EnergyPro" serverSearch={asking} filteredCount={0} pagedRows={[]} />,
    );
    const clear = screen.getByRole('button', {name: 'Clear Search'});
    clear.focus();
    // The visitor clicks blank page space: focus leaves Clear Search, which is still there. (The window keeps focus;
    // jsdom answers hasFocus() from the focused element, which it clears before the blur.)
    const hasFocus = vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    clear.blur();
    hasFocus.mockRestore();

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
});
