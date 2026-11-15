import {useState} from 'react';
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {useProjectGridTable} from '@/features/projects/components/grid/state/useProjectGridTable';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {baseProps, makeRows} from '@/__tests__/features/projects/components/grid/table/a11y/a11yFixtures';

// What a screen reader or keyboard user meets in the grid: names that say which project a control belongs to,
// focus that stays on the page, one message for View All Details, and no controls for rows that are not there.

const {fetchDetail} = vi.hoisted(() => ({fetchDetail: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: fetchDetail,
}));

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
    expect(screen.getAllByText('Loading project details…')).toHaveLength(3);
    expect(screen.queryAllByRole('status')).toHaveLength(0);
    expect(message).toHaveTextContent('All details shown.');

    fireEvent.click(screen.getByRole('button', {name: 'Hide All Details'}));
    expect(message).toHaveTextContent('All details hidden.');

    // A row opened by its own button still says it is loading.
    fireEvent.click(screen.getByRole('button', {name: 'Details for Project 1'}));
    expect(screen.getByRole('status')).toHaveTextContent('Loading project details…');
  });

  it('says it is loading the rows', () => {
    render(<ProjectGridTable {...baseProps} loading />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading project data…');
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
    expect(screen.getByRole('status')).toHaveTextContent('Loading project details…');
  });

  describe('Try Again', () => {
    const LOAD_ERROR = "We couldn't load the projects. Please try again.";
    const onRetry = vi.fn();
    const failed = <ProjectGridTable {...baseProps} error={LOAD_ERROR} onRetry={onRetry} />;
    const reloading = <ProjectGridTable {...baseProps} loading onRetry={onRetry} />;

    beforeEach(() => onRetry.mockClear());

    /** Presses Try Again as a keyboard user does: the button has focus first. */
    const pressTryAgain = () => {
      const button = screen.getByRole('button', {name: 'Try Again'});
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

    it('returns focus to Try Again when the load fails again, and to the empty message when no rows come back', () => {
      stubGridLayout('desktop');
      const {rerender} = render(failed);

      pressTryAgain();
      rerender(reloading);
      rerender(failed);
      expect(document.activeElement).toBe(screen.getByRole('button', {name: 'Try Again'}));

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
