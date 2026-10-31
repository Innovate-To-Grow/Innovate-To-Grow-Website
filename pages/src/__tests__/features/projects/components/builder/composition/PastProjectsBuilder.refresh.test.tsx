import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {useState} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Alpha Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

const ROWS: ProjectGridRow[] = [
  makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'}),
  makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
  makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'}),
];
const RAW_ERROR = 'Request failed with status code 503';
const REFRESH_FAILED = /This table was not refreshed: the past-project archive could not be loaded/;

const searchTable = (name: string) =>
  screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;

interface Archive {
  rows: ProjectGridRow[];
  loading: boolean;
  error: string | null;
}

/** The builder over an archive whose first load failed; Try again loads it again, as usePastProjectGridData does. */
const RetryHarness = () => {
  const [archive, setArchive] = useState<Archive>({rows: [], loading: false, error: RAW_ERROR});
  return (
    <>
      <PastProjectsBuilder
        {...archive}
        onRefreshRows={() => setArchive({rows: [], loading: true, error: null})}
        onCreateShare={vi.fn()}
      />
      <button type="button" onClick={() => setArchive({rows: [], loading: false, error: RAW_ERROR})}>
        Fail the load
      </button>
      <button type="button" onClick={() => setArchive({rows: ROWS, loading: false, error: null})}>
        Finish the load
      </button>
    </>
  );
};

describe('PastProjectsBuilder — refreshing a search table', () => {
  const onRefreshRows = vi.fn();
  const builder = (rows: ProjectGridRow[], error: string | null) => (
    <PastProjectsBuilder
      rows={rows}
      loading={false}
      error={error}
      onRefreshRows={onRefreshRows}
      onCreateShare={vi.fn()}
    />
  );

  beforeEach(() => {
    mockUseAuth.mockReturnValue({isAuthenticated: false, isInitializing: false, unverified: false, user: null});
    onRefreshRows.mockReset();
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it('keeps every table and its work when a refresh fails, and says so in the table that asked', () => {
    // The archive hook keeps serving the rows it had when a refetch fails, and reports the error.
    const {rerender} = render(builder(ROWS, null));
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    fireEvent.change(within(searchTable('Search Table 1')).getByRole('searchbox'), {target: {value: 'Alpha'}});
    fireEvent.click(within(searchTable('Search Table 2')).getAllByLabelText('Select Charlie Project')[0]);

    fireEvent.click(within(searchTable('Search Table 2')).getByRole('button', {name: 'Refresh Search Table'}));
    expect(onRefreshRows).toHaveBeenCalledTimes(1);
    rerender(builder(ROWS, RAW_ERROR));

    const table1 = within(searchTable('Search Table 1'));
    const table2 = within(searchTable('Search Table 2'));
    expect(table1.getByRole('searchbox')).toHaveValue('Alpha');
    expect(table2.getAllByLabelText('Select Charlie Project')[0]).toBeChecked();
    expect(table2.getByRole('alert')).toHaveTextContent(REFRESH_FAILED);
    expect(table1.queryByText(REFRESH_FAILED)).toBeNull();
    expect(screen.queryByText(/refreshed from the latest/)).toBeNull();
    expect(screen.queryByText(/Refreshing this search table/)).toBeNull();
    expect(screen.queryByText(RAW_ERROR)).toBeNull();
    expect(screen.getByRole('button', {name: '+ Search Table'})).toBeEnabled();

    // Refresh is the retry: while it runs the failure note goes, and the fresh archive resets the table.
    fireEvent.click(table2.getByRole('button', {name: 'Refresh Search Table'}));
    rerender(builder(ROWS, null));
    expect(table2.queryByText(REFRESH_FAILED)).toBeNull();
    rerender(builder([...ROWS, makeRow({team_number: 'T04', project_title: 'Delta Project'})], null));
    expect(within(searchTable('Search Table 2')).getAllByText('Delta Project').length).toBeGreaterThan(0);
    expect(screen.getByText('Search table refreshed from the latest past-project archive.')).toBeInTheDocument();
  });

  it('reloads every table that asked before the refetch landed', () => {
    const {rerender} = render(builder(ROWS, null));
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    for (const name of ['Search Table 1', 'Search Table 2']) {
      fireEvent.click(within(searchTable(name)).getByRole('button', {name: 'Refresh Search Table'}));
    }

    rerender(builder([...ROWS, makeRow({team_number: 'T04', project_title: 'Delta Project'})], null));

    expect(within(searchTable('Search Table 1')).getAllByText('Delta Project').length).toBeGreaterThan(0);
    expect(within(searchTable('Search Table 2')).getAllByText('Delta Project').length).toBeGreaterThan(0);
    expect(within(searchTable('Search Table 3')).queryAllByText('Delta Project')).toHaveLength(0);
    expect(screen.getByText('Search tables refreshed from the latest past-project archive.')).toBeInTheDocument();
  });

  it('explains a first load that failed in plain words and offers to try again', () => {
    render(builder([], RAW_ERROR));

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The past-project archive could not be loaded. Check your connection and try again.');
    expect(screen.queryByText(RAW_ERROR)).toBeNull();
    expect(screen.getByRole('button', {name: '+ Search Table'})).toBeDisabled();
    fireEvent.click(within(alert).getByRole('button', {name: 'Try again'}));
    expect(onRefreshRows).toHaveBeenCalledTimes(1);
  });

  it('keeps Try again, and its focus, while the retry loads, then hands focus to the Search Tables heading', () => {
    render(<RetryHarness />);
    const tryAgain = screen.getByRole('button', {name: 'Try again'});
    tryAgain.focus();

    fireEvent.click(tryAgain);
    // Pressing it again while it loads starts nothing more.
    fireEvent.click(tryAgain);
    expect(tryAgain).toBeInTheDocument();
    expect(tryAgain).toHaveFocus();
    expect(tryAgain).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Loading past projects…');
    expect(screen.getAllByText('Loading past projects…')).toHaveLength(1);

    // A retry that fails again says so in the same alert, and Try again works again.
    fireEvent.click(screen.getByRole('button', {name: 'Fail the load'}));
    expect(screen.getByRole('alert')).toHaveTextContent('The past-project archive could not be loaded.');
    expect(tryAgain).toHaveFocus();
    expect(tryAgain).not.toHaveAttribute('aria-disabled');

    fireEvent.click(tryAgain);
    fireEvent.click(screen.getByRole('button', {name: 'Finish the load'}));
    expect(tryAgain).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('heading', {level: 2, name: 'Search Tables'})).toHaveFocus();
    expect(searchTable('Search Table')).toBeInTheDocument();
  });
});
