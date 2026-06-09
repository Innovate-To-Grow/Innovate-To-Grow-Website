import {fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it} from 'vitest';

import {SheetsDataTable} from '@/components/ui/SheetsDataTable/SheetsDataTable';
import type {SheetRow} from '@/components/ui/SheetsDataTable/types';

const makeRow = (index: number, overrides: Partial<SheetRow> = {}): SheetRow => ({
  Track: `Track ${index % 3}`,
  Order: String(index),
  'Year-Semester': index % 2 === 0 ? '2026 Spring' : '2025 Fall',
  Class: index % 2 === 0 ? 'ENGR 190' : 'CSE 120',
  'Team#': `T-${String(index).padStart(2, '0')}`,
  TeamName: `Team ${String.fromCharCode(64 + index)}`,
  'Project Title': `Project ${index}`,
  Organization: index === 12 ? 'Special Lab' : 'UC Merced',
  Industry: index % 2 === 0 ? 'Agriculture' : 'Robotics',
  Abstract: index === 1 ? 'Detailed project abstract' : '',
  'Student Names': index === 1 ? 'Ada Lovelace, Grace Hopper' : '',
  'Showcase Participation': 'Yes',
  NameTitle: `Project ${index} owner`,
  ...overrides,
});

const rows = Array.from({length: 12}, (_, index) => makeRow(index + 1));

const renderTable = (props: Partial<Parameters<typeof SheetsDataTable>[0]> = {}, route = '/') =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <SheetsDataTable rows={rows} {...props} />
    </MemoryRouter>,
  );

describe('SheetsDataTable', () => {
  it('renders loading and error states before table content', () => {
    const loading = renderTable({loading: true});
    expect(screen.getByText('Loading project data...')).toBeInTheDocument();
    loading.unmount();

    renderTable({error: 'Could not load projects'});
    expect(screen.getByText('Could not load projects')).toBeInTheDocument();
  });

  it('filters rows from an initial URL search parameter and resets the count on input changes', () => {
    renderTable({}, '/?value=special');

    expect(screen.getByPlaceholderText('Search projects...')).toHaveValue('special');
    expect(screen.getByText('1 of 12 projects')).toBeInTheDocument();
    expect(screen.getByText('Special Lab')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search projects...'), {
      target: {value: 'robotics'},
    });

    expect(screen.getByText('6 of 12 projects')).toBeInTheDocument();
  });

  it('sorts, expands detail rows, and paginates project rows', () => {
    const {container} = renderTable();

    expect(screen.getByText('12 of 12 projects')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Team Name'));
    const firstBodyRow = container.querySelector('tbody tr');
    expect(firstBodyRow).toHaveTextContent('Team A');

    fireEvent.click(within(firstBodyRow as HTMLElement).getByText('▼'));
    expect(screen.getByText(/Abstract:/)).toBeInTheDocument();
    expect(screen.getByText(/Detailed project abstract/)).toBeInTheDocument();
    expect(screen.getByText(/Ada Lovelace, Grace Hopper/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Next'}));
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Next'})).toBeDisabled();

    fireEvent.click(screen.getByRole('button', {name: 'Previous'}));
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
  });
});
