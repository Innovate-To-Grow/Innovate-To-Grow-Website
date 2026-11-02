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

  it('uses semantic sort and disclosure buttons and preserves the expanded row through sorting', () => {
    render(
      <MemoryRouter>
        <SheetsDataTable
          rows={[
            makeRow('Zulu Project', '2', 'Zulu abstract'),
            makeRow('Alpha Project', '1', 'Alpha abstract'),
          ]}
        />
      </MemoryRouter>,
    );

    const projectHeader = screen
      .getByRole('button', {name: 'Project Title'})
      .closest('th');
    expect(projectHeader).toHaveAttribute('aria-sort', 'none');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Show details for Zulu Project',
      }),
    );
    expect(screen.getByText('Zulu abstract')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Project Title'}));

    expect(projectHeader).toHaveAttribute('aria-sort', 'ascending');
    // The sorted header carries the arrow class; its column is not shaded (as in the projects table), so its
    // cells carry no class of their own.
    expect(projectHeader).toHaveClass('sdt-sorted-asc');
    expect(
      screen.getByRole('cell', {name: 'Alpha Project'}),
    ).not.toHaveClass('is-sorted-col');
    expect(
      screen.getByRole('columnheader', {name: 'Details'}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: 'Hide details for Zulu Project'}),
    ).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Zulu abstract')).toBeInTheDocument();
    expect(screen.queryByText('Alpha abstract')).toBeNull();
  });

  it('preserves expanded identity across inserted and reordered source rows', () => {
    const zulu = makeRow('Zulu Project', '2', 'Zulu abstract');
    const alpha = makeRow('Alpha Project', '1', 'Alpha abstract');
    const {rerender} = render(
      <MemoryRouter>
        <SheetsDataTable rows={[zulu, alpha]} />
      </MemoryRouter>,
    );
    const disclosure = screen.getByRole('button', {
      name: 'Show details for Zulu Project',
    });
    fireEvent.click(disclosure);
    const detailId = disclosure.getAttribute('aria-controls');

    rerender(
      <MemoryRouter>
        <SheetsDataTable
          rows={[
            makeRow('Beta Project', '3', 'Beta abstract'),
            alpha,
            zulu,
          ]}
        />
      </MemoryRouter>,
    );

    const expanded = screen.getByRole('button', {
      name: 'Hide details for Zulu Project',
    });
    expect(expanded).toHaveAttribute('aria-expanded', 'true');
    expect(expanded).toHaveAttribute('aria-controls', detailId);
    expect(screen.getByText('Zulu abstract')).toBeInTheDocument();
  });

  it('labels the search control and current result count for assistive technology', () => {
    render(
      <MemoryRouter>
        <SheetsDataTable
          rows={[
            makeRow('Zulu Project', '2', 'Zulu abstract'),
            makeRow('Alpha Project', '1', 'Alpha abstract'),
          ]}
        />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search projects'}), {
      target: {value: 'Alpha'},
    });
    expect(screen.getByText('1 of 2 projects')).toHaveAttribute(
      'aria-live',
      'polite',
    );
    const table = screen.getByRole('table');
    expect(within(table).getByText('Alpha Project')).toBeInTheDocument();
    expect(within(table).queryByText('Zulu Project')).toBeNull();
  });

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

  it('uses the ellipsis glyph in the search placeholder', () => {
    render(
      <MemoryRouter>
        <SheetsDataTable rows={[makeRow('Alpha Project', '1', 'Alpha abstract')]} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('searchbox', {name: 'Search projects'})).toHaveAttribute(
      'placeholder',
      'Search projects…',
    );
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

  it('draws Details as the square outline icon button whose arrow turns when the row opens', () => {
    render(
      <MemoryRouter>
        <SheetsDataTable rows={[makeRow('Alpha Project', '1', 'Alpha abstract')]} />
      </MemoryRouter>,
    );

    const details = screen.getByRole('button', {name: 'Show details for Alpha Project'});
    expect(details).toHaveClass('sdt-expand-button');
    expect(details).toHaveAttribute('aria-expanded', 'false');
    expect(details.querySelector('.sdt-expand-icon')).toHaveAttribute('aria-hidden', 'true');

    fireEvent.click(details);
    expect(details).toHaveAttribute('aria-expanded', 'true');
    expect(details.closest('tr')).toHaveClass('sdt-row', 'is-expanded');
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
