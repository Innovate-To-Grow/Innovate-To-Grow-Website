import type {ReactElement} from 'react';
import {act, cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {
  PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridRow,
  type ProjectGridSortDirection,
} from '@/features/projects/components/grid/contracts/projectGrid';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {shownText, translatePage} from '@/__tests__/features/projects/fixtures/pageTranslation';

// Chrome's Translate replaces the page's text nodes with its own elements. Before each text became the only child
// of its element, clearing a search on a translated page threw "removeChild" and React Router replaced the page
// with its error screen; counts and labels kept their old text.

const rows = createProjectGridItems(
  Array.from(
    {length: 3},
    (_, index): ProjectGridRow => ({
      id: `project-${index}`,
      semester_label: '2026 Fall',
      class_code: 'CAP',
      team_number: `10${index}`,
      team_name: `Team ${index}`,
      project_title: `Project ${index}`,
      organization: 'Acme',
      industry: 'Energy',
      abstract: 'An abstract.',
      student_names: 'Ada',
      is_presenting: 'Yes',
    }),
  ),
  'translated',
);

const gridProps = {
  columns: PROJECT_GRID_COLUMNS,
  rows,
  pagedRows: rows,
  filteredCount: 75,
  totalCount: 75,
  search: '',
  sortField: 'class_code' as ProjectGridColumnKey,
  sortDirection: 'asc' as ProjectGridSortDirection,
  onSearchChange: vi.fn(),
  onSortChange: vi.fn(),
  expandedKeys: new Set<string>(),
  onToggleExpanded: vi.fn(),
  page: 0,
  totalPages: 8,
  onPageChange: vi.fn(),
  pageSize: 10,
  pageSizeOptions: [10, 25],
  onPageSizeChange: vi.fn(),
  noResultsHint: 'Older projects are in Past Projects.',
};

/** Renders, lets the "translator" run, then re-renders, collecting what React threw on the translated page. */
function renderTranslated(first: ReactElement) {
  const errors: unknown[] = [];
  const onError = (event: ErrorEvent) => {
    errors.push(event.error);
    event.preventDefault();
  };
  window.addEventListener('error', onError);
  const view = render(first);
  translatePage(view.container);
  const update = (next: ReactElement) => {
    try {
      act(() => view.rerender(next));
    } catch (error) {
      errors.push(error);
    }
  };
  const stop = () => window.removeEventListener('error', onError);
  return {...view, update, errors, stop};
}

const count = (container: HTMLElement) => shownText(container.querySelector('.project-grid-count'));

describe('ProjectGridTable on a translated page', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('survives clearing a search, and the count follows', () => {
    const view = renderTranslated(<ProjectGridTable {...gridProps} search="ag" filteredCount={32} />);
    view.update(<ProjectGridTable {...gridProps} />);
    view.stop();

    expect(view.errors).toEqual([]);
    expect(count(view.container)).toBe('75 projects · showing 1–10');
  });

  it('survives a search that ends with no results, and says so', () => {
    const view = renderTranslated(<ProjectGridTable {...gridProps} search="xq" filteredCount={3} />);
    view.update(<ProjectGridTable {...gridProps} search="xqz" filteredCount={0} pagedRows={[]} totalPages={1} />);
    view.update(
      <ProjectGridTable {...gridProps} search="xqzv" filteredCount={0} pagedRows={[]} totalPages={1} activeFilters={['Energy']} />,
    );
    view.stop();

    expect(view.errors).toEqual([]);
    expect(count(view.container)).toBe('0 of 75 projects match “xqzv” in Energy');
    expect(shownText(view.container.querySelector('h2'))).toBe('No projects match “xqzv” in Energy');
    expect(shownText(view.container.querySelector('.itg-empty-state-actions button'))).toBe('Clear search and filters');
  });

  it('adds and takes away the note that the abstracts were not searched', () => {
    const tooBroad = {pending: false, addedRowsKey: null, tooBroad: true};
    const view = renderTranslated(<ProjectGridTable {...gridProps} search="tea" filteredCount={32} />);
    view.update(<ProjectGridTable {...gridProps} search="team" filteredCount={30} serverSearch={tooBroad} />);
    const shown = count(view.container);
    view.update(<ProjectGridTable {...gridProps} search="teams" filteredCount={3} />);
    view.stop();

    expect(view.errors).toEqual([]);
    expect(shown).toBe(
      '30 of 75 projects match “team” · showing 1–10Abstracts were not searched: too many projects match. Try a longer search.',
    );
    expect(count(view.container)).toBe('3 of 75 projects match “teams” · showing 1–3');
  });

  it('keeps the count and the pager status in step with the page', () => {
    stubGridLayout('phone');
    const view = renderTranslated(<ProjectGridTable {...gridProps} />);
    view.update(<ProjectGridTable {...gridProps} page={1} />);
    view.stop();

    expect(view.errors).toEqual([]);
    expect(count(view.container)).toBe('75 projects · showing 11–20');
    expect(shownText(view.container.querySelector('.project-grid-pager-status'))).toBe('Page 2 of 8');
  });

  it("updates a phone card's details toggle when it opens", () => {
    stubGridLayout('phone');
    const view = renderTranslated(<ProjectGridTable {...gridProps} />);
    view.update(<ProjectGridTable {...gridProps} expandedKeys={new Set([rows[0].__key])} />);
    view.stop();

    expect(view.errors).toEqual([]);
    const toggle = view.container.querySelector('.project-grid-mobile-card .project-grid-detail-button');
    // The visible label and arrow; a hidden " for <title>" names the project for screen readers.
    expect(shownText(toggle)).toBe(`Hide details for ${rows[0].project_title} ▴`);
  });
});
