import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';
import {MemoryRouter} from 'react-router';
import {SheetsDataTable} from '@/components/SheetsDataTable/SheetsDataTable';
import type {SheetRow} from '@/components/SheetsDataTable/types';

const makeRow = (
  title: string,
  team: string,
  abstract: string,
): SheetRow => ({
  Track: 'Engineering',
  Order: team,
  'Year-Semester': '2026 Spring',
  Class: 'ENGR 190',
  'Team#': team,
  TeamName: `Team ${team}`,
  'Project Title': title,
  Organization: 'UC Merced',
  Industry: 'Education',
  Abstract: abstract,
  'Student Names': `${title} Students`,
  'Showcase Participation': 'Yes',
  NameTitle: title,
});

describe('SheetsDataTable accessibility and row identity', () => {
  afterEach(cleanup);

  it('shows the shared loading indicator, with the ellipsis glyph, in a status line while rows load', () => {
    render(
      <MemoryRouter>
        <SheetsDataTable rows={[]} loading />
      </MemoryRouter>,
    );

    const status = screen.getByRole('status');
    expect(status).toHaveClass('sdt-loading');
    expect(status).toHaveTextContent('Loading project data…');
    const indicator = status.querySelector('.loading-indicator');
    expect(indicator).not.toBeNull();
    expect(indicator?.querySelector('.loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('pages with the site pager: outline steps, the first page\'s Previous disabled', () => {
    const rows = Array.from({length: 12}, (_, index) =>
      makeRow(`Project ${String(index + 1).padStart(2, '0')}`, String(index + 1), `Abstract ${index + 1}`),
    );
    render(
      <MemoryRouter>
        <SheetsDataTable rows={rows} />
      </MemoryRouter>,
    );

    const pager = screen.getByRole('navigation', {name: 'Project pages'});
    expect(pager).toHaveClass('itg-pagination');
    const previous = within(pager).getByRole('button', {name: 'Previous'});
    const next = within(pager).getByRole('button', {name: 'Next'});
    expect(previous).toHaveClass('itg-pagination-link');
    expect(next).toHaveClass('itg-pagination-link');
    expect(previous).toBeDisabled();
    expect(within(pager).getByText('Page 1 of 2')).toHaveClass('itg-pagination-info');

    fireEvent.click(next);
    expect(within(pager).getByText('Page 2 of 2')).toBeInTheDocument();
    expect(next).toBeDisabled();
    expect(previous).toBeEnabled();
  });

  it('says so inside the table when there are no rows or no matches, as DataTables does', () => {
    const {rerender} = render(
      <MemoryRouter>
        <SheetsDataTable rows={[]} />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('cell', {name: 'No data available in table'}),
    ).toHaveAttribute('colspan', String(9 + 1));

    rerender(
      <MemoryRouter>
        <SheetsDataTable rows={[makeRow('Alpha Project', '1', 'Alpha abstract')]} />
      </MemoryRouter>,
    );
    expect(screen.queryByText('No data available in table')).toBeNull();

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search projects'}), {
      target: {value: 'nothing like this'},
    });
    expect(
      screen.getByRole('cell', {name: 'No matching records found'}),
    ).toBeInTheDocument();
  });
});
