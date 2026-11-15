import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {answered, asking, baseProps, makeRows, rows, sortOptions} from '@/__tests__/features/projects/components/grid/table/a11y/a11yFixtures';

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

  it('still moves focus to the count line when the visitor was in another window as the answer landed', () => {
    stubGridLayout('desktop');
    const {container, rerender} = render(
      <ProjectGridTable {...baseProps} search="EnergyPro" serverSearch={asking} filteredCount={0} pagedRows={[]} />,
    );
    const clear = screen.getByRole('button', {name: 'Clear Search'});
    clear.focus();
    // The visitor switches to another window: the control gets a blur but stays the page's focused element.
    const hasFocus = vi.spyOn(document, 'hasFocus').mockReturnValue(false);
    fireEvent.blur(clear);
    hasFocus.mockRestore();
    expect(document.activeElement).toBe(clear);

    rerender(
      <ProjectGridTable
        {...baseProps}
        search="EnergyPro"
        serverSearch={answered('a11y-1')}
        filteredCount={1}
        pagedRows={[rows[1]]}
      />,
    );
    expect(document.activeElement).toBe(container.querySelector('.project-grid-count'));
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
});
