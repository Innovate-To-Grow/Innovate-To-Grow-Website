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
});
