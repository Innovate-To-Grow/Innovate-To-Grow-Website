import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {CurrentProjectsView} from '@/features/projects/components/views/pages/CurrentProjectsView';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const row = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
  id: 'project-1',
  semester_label: '2026-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'HVAC Regulators',
  project_title: 'HVAC Design',
  organization: 'ASHRAE',
  industry: 'Energy',
  abstract: 'An HVAC abstract.',
  student_names: 'Brian Arroyo, Joel Gonzalez',
  is_presenting: 'Yes',
  ...overrides,
});

const ROWS: ProjectGridRow[] = [
  row(),
  row({
    id: 'project-2',
    team_number: '102',
    team_name: 'Almond Peelerz',
    project_title: 'Almond Optimization',
    organization: 'Blue Diamond',
    industry: 'Food Processing',
  }),
  row({
    id: 'project-3',
    semester_label: '',
    class_code: 'CSE',
    team_number: '301',
    team_name: 'Bagception',
    project_title: 'Bagging Bags',
    organization: 'Bolthouse',
    industry: 'Food Processing',
    is_presenting: 'No',
  }),
];

const renderView = (
  props: Partial<Parameters<typeof CurrentProjectsView>[0]> = {},
  initialEntries: string[] = ['/current-projects'],
) =>
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <CurrentProjectsView
        title="Current Projects"
        lede="Browse this semester's projects."
        rows={ROWS}
        loading={false}
        error={null}
        classLabels={{CAP: 'Engineering Capstone'}}
        namespace="current-projects"
        emptyTitle="No current projects yet"
        emptyMessage="This semester's projects appear here once the schedule is published."
        {...props}
      />
    </MemoryRouter>,
  );

const desktopTable = (container: HTMLElement) => container.querySelector('.project-grid-table-wrap') as HTMLElement;
describe('CurrentProjectsView', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the title, a meta line computed from the rows, and the lede', () => {
    const {container} = renderView();
    // The chat launcher tucks away over the list's text and rows, not only its controls (useLauncherYield).
    expect(container.querySelector('.projects-page')).toHaveAttribute('data-launcher-avoid', '');

    expect(screen.getByRole('heading', {level: 1, name: 'Current Projects'})).toBeInTheDocument();
    expect(screen.getByText('Spring 2026 · 3 projects · 2 teams presenting at the showcase')).toBeInTheDocument();
    expect(screen.getByText("Browse this semester's projects.")).toHaveClass('itg-lead');
  });

  it('counts teams on the presenting-teams variant', () => {
    renderView({countLabel: 'teams', rows: ROWS.slice(0, 2)});

    expect(screen.getByText('Spring 2026 · 2 teams presenting')).toBeInTheDocument();
  });

  it('shows the team code, a linked title with its team name, and the organization and industry', () => {
    const {container} = renderView();
    const table = within(desktopTable(container));

    expect(table.getByRole('columnheader', {name: 'Team'})).toBeInTheDocument();
    expect(table.getByText('CAP 101')).toBeInTheDocument();
    expect(table.getByRole('link', {name: 'HVAC Design'})).toHaveAttribute('href', '/projects/project-1');
    expect(table.getByText('HVAC Regulators')).toHaveClass('project-grid-team-name');
    expect(table.getByText('ASHRAE')).toBeInTheDocument();
  });

  it('expands a row with its abstract, team members and a link to the project page', () => {
    const {container} = renderView();
    const table = within(desktopTable(container));

    // Each row's Details button and page link are named after its project.
    fireEvent.click(table.getByRole('button', {name: 'Details for HVAC Design'}));

    expect(table.getByText('An HVAC abstract.')).toBeInTheDocument();
    expect(table.getByText('Brian Arroyo, Joel Gonzalez')).toBeInTheDocument();
    expect(table.getByRole('link', {name: 'Open the Project Page for HVAC Design'})).toHaveAttribute(
      'href',
      '/projects/project-1',
    );
    expect(table.queryByRole('button', {name: /^Copy Project Link/})).toBeNull();
  });

  it('shows the loading and error states without a meta line, keeping its room while loading', () => {
    const {container, rerender} = renderView({loading: true, rows: []});
    expect(screen.getByRole('status')).toHaveTextContent('Loading project data…');
    expect(screen.queryByText(/projects ·/)).toBeNull();
    // A blank line, so the lede and the grid do not move down when the real one appears.
    const meta = container.querySelector('.itg-page-meta') as HTMLElement;
    expect(meta.textContent).toBe('\u00a0');
    expect(meta).toHaveAttribute('aria-hidden', 'true');
    expect(meta.nextElementSibling).toHaveClass('itg-lead');

    rerender(
      <MemoryRouter>
        <CurrentProjectsView
          title="Current Projects"
          lede="Lede."
          rows={[]}
          loading={false}
          error="Schedule down"
          namespace="current-projects"
          emptyTitle="No current projects yet"
          emptyMessage="This semester's projects appear here once the schedule is published."
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Schedule down');
    expect(screen.queryByRole('button', {name: 'Try Again'})).toBeNull();
  });

  it('offers to load the projects again after an error', () => {
    const onRetry = vi.fn();
    renderView({rows: [], error: "We couldn't load the projects.", onRetry});

    const tryAgain = screen.getByRole('button', {name: 'Try Again'});
    // An outline button: the failure sits inside the page and does not outrank its own actions.
    expect(tryAgain).toHaveClass('itg-btn', 'itg-btn-outline');
    fireEvent.click(tryAgain);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('shows an empty state like the no-results one when there are no projects yet', () => {
    const {container} = renderView({
      rows: [],
      emptyActions: (
        <a className="itg-btn itg-btn-outline" href="/past-projects">
          Search Past Projects
        </a>
      ),
    });

    const heading = screen.getByRole('heading', {level: 2, name: 'No current projects yet'});
    expect(heading).toHaveClass('itg-empty-state-title');
    const emptyState = heading.closest('.itg-empty-state') as HTMLElement;
    expect(emptyState).toHaveClass('project-grid-empty-state');
    expect(within(emptyState).getByText("This semester's projects appear here once the schedule is published.")).toHaveClass(
      'itg-empty-state-text',
    );
    expect(within(emptyState).getByRole('link', {name: 'Search Past Projects'})).toHaveAttribute('href', '/past-projects');
    expect(container.querySelector('.project-grid-empty')).toBeNull();
    expect(screen.queryByText(/projects ·/)).toBeNull();
  });
});
