import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {RouterProvider, createMemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {CurrentProjectsView} from '@/features/projects/components/views/pages/CurrentProjectsView';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// The Class and Industry filters in use, shown as removable chips between the filter well and the results.

// 15 CAP and 15 CSE teams, alternating between two industries.
const ROWS: ProjectGridRow[] = Array.from({length: 30}, (_, index) => ({
  id: `0000000${index}`.slice(-8) + '-0000-4000-8000-000000000000',
  semester_label: '2026 Fall',
  class_code: index < 15 ? 'CAP' : 'CSE',
  team_number: String(101 + (index % 15)),
  team_name: `Team ${index + 1}`,
  project_title: `Project ${index + 1}`,
  organization: `Org ${index + 1}`,
  industry: index % 2 ? 'Energy' : 'Agriculture',
  abstract: '',
  student_names: '',
  is_presenting: 'Yes',
}));

const renderAt = (entry: string, rows: ProjectGridRow[] = ROWS) => {
  const router = createMemoryRouter(
    [
      {
        path: '/current-projects',
        element: (
          <CurrentProjectsView
            title="Current Projects"
            lede="Lede."
            rows={rows}
            loading={false}
            error={null}
            classLabels={{CAP: 'Engineering Capstone'}}
            namespace="current-projects"
            emptyTitle="No current projects yet"
            emptyMessage="This semester's projects appear here once the schedule is published."
          />
        ),
      },
    ],
    {initialEntries: [entry]},
  );
  const view = render(<RouterProvider router={router} />);
  return {router, container: view.container};
};

const chips = () => screen.getByRole('group', {name: 'Active filters'});
const countLine = () => document.querySelector('.project-grid-count') as HTMLElement;

describe('ActiveFilterChips', () => {
  beforeEach(() => {
    vi.stubGlobal('scrollTo', vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows no chips, and no toolbar, while no filter is in use', () => {
    const {container} = renderAt('/current-projects?value=Project');

    expect(screen.queryByRole('group', {name: 'Active filters'})).toBeNull();
    expect(container.querySelector('.project-grid-toolbar')).toBeNull();
  });

  it('shows one chip per filter, after the filter well and before the results', () => {
    const {container} = renderAt('/current-projects?class=CAP');

    const chip = within(chips()).getByRole('button', {name: 'Class: Engineering Capstone (CAP), remove filter'});
    expect(chip).toHaveClass('itg-btn', 'itg-btn-outline', 'project-grid-filter-chip');
    expect(chip).toHaveTextContent('Class: Engineering Capstone (CAP)');
    // With one chip, "Clear Filters" would do exactly what the chip does.
    expect(screen.queryByRole('button', {name: 'Clear Filters'})).toBeNull();

    const toolbar = container.querySelector('.project-grid-toolbar') as HTMLElement;
    expect(toolbar).toContainElement(chips());
    expect(toolbar.previousElementSibling).toHaveClass('project-grid-controls');
    expect(toolbar.nextElementSibling).toHaveClass('project-grid-results-bar');
  });

  it('removes its filter, focuses the filter select, goes back to page 1 and updates the URL', async () => {
    const {router} = renderAt('/current-projects?class=CAP&page=2');
    expect(countLine()).toHaveTextContent('15 of 30 projects in Engineering Capstone (CAP) · showing 11–15');

    fireEvent.click(screen.getByRole('button', {name: 'Class: Engineering Capstone (CAP), remove filter'}));

    expect(document.activeElement).toBe(screen.getByLabelText('Class'));
    expect(screen.getByLabelText('Class')).toHaveValue('');
    expect(countLine()).toHaveTextContent('30 projects · showing 1–10');
    expect(screen.queryByRole('group', {name: 'Active filters'})).toBeNull();
    await waitFor(() => expect(router.state.location.search).toBe(''));
  });

  it('moves focus to the chip that stays when one of two is removed', () => {
    renderAt('/current-projects?class=CAP&industry=Energy');
    const industryChip = screen.getByRole('button', {name: 'Industry: Energy, remove filter'});

    fireEvent.click(screen.getByRole('button', {name: 'Class: Engineering Capstone (CAP), remove filter'}));

    // The same element: the chip that stays keeps its node.
    expect(document.activeElement).toBe(industryChip);
    expect(industryChip).toBeInTheDocument();
    expect(screen.getByLabelText('Industry')).toHaveValue('Energy');
    expect(screen.queryByRole('button', {name: 'Clear Filters'})).toBeNull();
  });

  it('clears both filters with Clear Filters and focuses the Class select', async () => {
    const {router} = renderAt('/current-projects?class=CAP&industry=Energy&page=2&per=5');

    const clear = within(chips()).getByRole('button', {name: 'Clear Filters'});
    expect(clear).toHaveClass('itg-btn-text');
    fireEvent.click(clear);

    expect(document.activeElement).toBe(screen.getByLabelText('Class'));
    expect(screen.getByLabelText('Class')).toHaveValue('');
    expect(screen.getByLabelText('Industry')).toHaveValue('');
    expect(countLine()).toHaveTextContent('30 projects · showing 1–5');
    await waitFor(() => expect(router.state.location.search).toBe('?per=5'));
  });

  describe('when the two filters match no project', () => {
    // One more CSE team, in an industry no CAP team is in.
    const rows = [...ROWS, {...ROWS[29], id: '00000030-0000-4000-8000-000000000000', industry: 'Water'}];

    it('leaves Clear Filters to the no-results state, keeping both chips', () => {
      const {container} = renderAt('/current-projects?class=CAP&industry=Water', rows);

      const clear = screen.getAllByRole('button', {name: 'Clear Filters'});
      expect(clear).toHaveLength(1);
      expect(container.querySelector('.project-grid-no-results')).toContainElement(clear[0]);
      expect(within(chips()).getAllByRole('button')).toHaveLength(2);

      fireEvent.click(clear[0]);

      expect(screen.getByLabelText('Class')).toHaveValue('');
      expect(screen.getByLabelText('Industry')).toHaveValue('');
      expect(screen.queryByRole('group', {name: 'Active filters'})).toBeNull();
    });

    it('offers only the no-results clear when a search is set as well', () => {
      renderAt('/current-projects?value=Project&class=CAP&industry=Water', rows);

      expect(screen.queryByRole('button', {name: 'Clear Filters'})).toBeNull();
      expect(screen.getByRole('button', {name: 'Clear Search and Filters'})).toBeInTheDocument();
      expect(within(chips()).getAllByRole('button')).toHaveLength(2);
    });

    it('offers Clear Filters among the chips again once a filter change brings rows back', () => {
      const {container} = renderAt('/current-projects?class=CAP&industry=Water', rows);

      fireEvent.change(screen.getByLabelText('Industry'), {target: {value: 'Energy'}});

      expect(container.querySelector('.project-grid-no-results')).toBeNull();
      expect(within(chips()).getByRole('button', {name: 'Clear Filters'})).toBeInTheDocument();
      expect(screen.getAllByRole('button', {name: 'Clear Filters'})).toHaveLength(1);
    });
  });
});
