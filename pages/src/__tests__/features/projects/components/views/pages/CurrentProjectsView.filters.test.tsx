import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

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

    fireEvent.click(screen.getByRole('button', {name: 'Clear Search and Filters'}));

    await waitFor(() => expect(countLine(container)).toHaveTextContent('3 projects · showing 1–3'));
    expect(screen.getByRole('searchbox')).toHaveValue('');
    expect(screen.getByLabelText('Class')).toHaveValue('');
  });
});
