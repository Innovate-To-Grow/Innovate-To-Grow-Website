import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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
const countLine = (container: HTMLElement) => container.querySelector('.project-grid-count') as HTMLElement;

describe('CurrentProjectsView', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the title, a meta line computed from the rows, and the lede', () => {
    renderView();

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
    expect(table.getByRole('link', {name: 'Open the project page for HVAC Design'})).toHaveAttribute(
      'href',
      '/projects/project-1',
    );
    expect(table.queryByRole('button', {name: /^Copy project link/})).toBeNull();
  });

  it('builds the Class and Industry filters from the rows and filters by them', async () => {
    const {container} = renderView();

    const classSelect = screen.getByLabelText('Class');
    expect(within(classSelect).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'All classes',
      'CSE',
      'Engineering Capstone (CAP)',
    ]);
    const industrySelect = screen.getByLabelText('Industry');
    expect(within(industrySelect).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'All industries',
      'Energy',
      'Food Processing',
    ]);

    fireEvent.change(classSelect, {target: {value: 'CAP'}});
    fireEvent.change(industrySelect, {target: {value: 'Food Processing'}});

    // The count names the filters that narrowed the rows.
    await waitFor(() =>
      expect(countLine(container)).toHaveTextContent('1 of 3 projects in Engineering Capstone (CAP) and Food Processing'),
    );
    expect(within(desktopTable(container)).getByText('Almond Optimization')).toBeInTheDocument();
    expect(within(desktopTable(container)).queryByText('HVAC Design')).toBeNull();
  });

  it('sorts by the Sort by select', () => {
    const {container} = renderView();

    fireEvent.change(screen.getByLabelText('Sort by'), {target: {value: 'project_title:asc'}});

    const titles = Array.from(desktopTable(container).querySelectorAll('.project-grid-title')).map(
      (title) => title.textContent,
    );
    expect(titles).toEqual(['Almond Optimization', 'Bagging Bags', 'HVAC Design']);
  });

  it('finds a team by the class name the Class filter shows', async () => {
    const {container} = renderView();

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'engineering capstone'}});

    await waitFor(() => expect(countLine(container)).toHaveTextContent('2 of 3 projects match “engineering capstone”'));
    expect(within(desktopTable(container)).queryByText('Bagging Bags')).toBeNull();
  });

  it('seeds the search from the ?value= parameter', () => {
    renderView({}, ['/current-projects?value=Bagging']);

    expect(screen.getByRole('searchbox')).toHaveValue('Bagging');
  });

  it('offers to clear the search, or to search past projects, when nothing matches', async () => {
    const {container} = renderView();

    fireEvent.change(screen.getByLabelText('Class'), {target: {value: 'CSE'}});
    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'hydroponics'}});

    // The Class filter is in use too: the message says so, rather than blaming the spelling alone.
    expect(
      await screen.findByRole('heading', {level: 2, name: 'No projects match “hydroponics” in CSE'}),
    ).toBeInTheDocument();
    expect(countLine(container)).toHaveTextContent('0 of 3 projects match “hydroponics” in CSE');
    expect(screen.getByText(/Older projects are in Past Projects\./)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Search Past Projects for “hydroponics”'})).toHaveAttribute(
      'href',
      '/past-projects?value=hydroponics',
    );
    expect(container.querySelector('.project-grid-table-wrap')).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: 'Clear search and filters'}));

    await waitFor(() => expect(countLine(container)).toHaveTextContent('3 projects · showing 1–3'));
    expect(screen.getByRole('searchbox')).toHaveValue('');
    expect(screen.getByLabelText('Class')).toHaveValue('');
  });

  it('shows the loading and error states without a meta line, keeping its room while loading', () => {
    const {container, rerender} = renderView({loading: true, rows: []});
    expect(screen.getByText('Loading project data...')).toBeInTheDocument();
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
    expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
  });

  it('offers to load the projects again after an error', () => {
    const onRetry = vi.fn();
    renderView({rows: [], error: "We couldn't load the projects.", onRetry});

    fireEvent.click(screen.getByRole('button', {name: 'Try again'}));
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
