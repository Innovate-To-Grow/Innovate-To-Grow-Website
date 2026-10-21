import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();
const authenticatedAuth = {
  isAuthenticated: true,
  isInitializing: false,
  unverified: false,
  user: {member_uuid: 'member-1', email: 'member@example.com'},
};

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/redirects')>();
  return {
    ...actual,
    buildLoginPath: (...args: unknown[]) => mockBuildLoginPath(...args),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
    hydrateProjectGridRowsSettled: (...args: unknown[]) => mockHydrateProjectGridRowsSettled(...args),
  };
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

const getMergedSection = () => {
  const heading = screen.queryByRole('heading', {name: /saved merged results/i});
  return heading ? (heading.closest('section') as HTMLElement) : null;
};

describe('PastProjectsBuilder — Save/Merge selection contract', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(authenticatedAuth);
    mockSearchPastProjectsWithAI.mockReset();
    mockBuildLoginPath.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset();
    // The builder keeps its draft in localStorage; clear it so drafts don't leak between tests.
    localStorage.clear();
    sessionStorage.clear();
    vi.spyOn(window, 'confirm').mockImplementation(() => {
      throw new Error('Past projects should use an in-page confirmation dialog.');
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('merges ONLY the checked rows, not the whole table', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    // No saved results yet.
    expect(getMergedSection()).toBeNull();

    // Check exactly one row, then Save Selected — the per-table merge button. (The grid renders a
    // desktop table and mobile cards, so each row's checkbox/label appears twice — target the first
    // match; both checkboxes map to the same row key.) There is no confirmation dialog anymore.
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(window.confirm).not.toHaveBeenCalled();

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    const mergedView = within(merged as HTMLElement);
    // Only the selected project is saved.
    expect(mergedView.getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(mergedView.queryByText('Alpha Project')).toBeNull();
    expect(mergedView.queryByText('Charlie Project')).toBeNull();
  });

  it('disables Save Selected until a row is selected and never merges everything by default', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /save selected/i});
    expect(mergeButton).toBeDisabled();

    // Selecting a row enables it.
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    expect(mergeButton).toBeEnabled();
  });

  it('does not toggle selection from desktop row body clicks', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /save selected/i});
    fireEvent.click(screen.getAllByText('Bravo Project')[0]);
    expect(mergeButton).toBeDisabled();

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    expect(mergeButton).toBeEnabled();
  });

  it('can undo search-table row deletion and refresh a standard search table', () => {
    const onRefreshRows = vi.fn();
    render(
      <PastProjectsBuilder
        rows={ROWS}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    const undoButton = screen.getByRole('button', {name: /undo row change/i});
    expect(undoButton).toBeDisabled();

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /remove from table/i}));

    expect(screen.queryByText('Bravo Project')).toBeNull();
    expect(undoButton).toBeEnabled();

    fireEvent.click(undoButton);
    expect(screen.getAllByText('Bravo Project').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', {name: /refresh search table/i}));
    expect(onRefreshRows).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Refreshing this search table/i)).toBeInTheDocument();
  });

  it('refreshes only the requesting search table and keeps other tables curated', () => {
    const onRefreshRows = vi.fn();
    const {rerender} = render(
      <PastProjectsBuilder
        rows={ROWS}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    // Open a second table and curate it: drop Bravo from table 2 only.
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table2 = screen
      .getByRole('heading', {level: 3, name: 'Search Table 2'})
      .closest('section') as HTMLElement;
    fireEvent.click(within(table2).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(table2).getByRole('button', {name: /remove from table/i}));
    expect(within(table2).queryAllByText('Bravo Project')).toHaveLength(0);

    // Ask table 1 to refresh — the parent starts a refetch while the stale rows stay mounted.
    const table1 = screen
      .getByRole('heading', {level: 3, name: 'Search Table 1'})
      .closest('section') as HTMLElement;
    fireEvent.click(within(table1).getByRole('button', {name: /refresh search table/i}));
    expect(onRefreshRows).toHaveBeenCalledTimes(1);

    // The refetch resolves with a new archive snapshot containing an extra project.
    const refreshedRows = [
      ...ROWS,
      makeRow({team_number: 'T04', team_name: 'Team Delta', project_title: 'Delta Project'}),
    ];
    rerender(
      <PastProjectsBuilder
        rows={refreshedRows}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    // Table 1 remounts with the fresh archive...
    const refreshedTable1 = screen
      .getByRole('heading', {level: 3, name: 'Search Table 1'})
      .closest('section') as HTMLElement;
    expect(within(refreshedTable1).getAllByText('Delta Project').length).toBeGreaterThan(0);

    // ...while table 2 keeps its local curation: Bravo stays deleted, Delta is not injected.
    const keptTable2 = screen
      .getByRole('heading', {level: 3, name: 'Search Table 2'})
      .closest('section') as HTMLElement;
    expect(within(keptTable2).queryAllByText('Bravo Project')).toHaveLength(0);
    expect(within(keptTable2).queryAllByText('Delta Project')).toHaveLength(0);
    expect(screen.getByText('Search table refreshed from the latest past-project archive.')).toBeInTheDocument();
  });

  it('seeds only the first search table with the search it was given', () => {
    render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} initialSearch="Bravo" onCreateShare={vi.fn()} />,
    );

    const table = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    expect(within(table).getByRole('searchbox')).toHaveValue('Bravo');

    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table2 = screen.getByRole('heading', {level: 3, name: 'Search Table 2'}).closest('section') as HTMLElement;
    expect(within(table2).getByRole('searchbox')).toHaveValue('');
  });

  it('heads the search tables with a section title and its add buttons', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const section = screen.getByRole('region', {name: 'Search Tables'});
    const addGroup = within(section).getByRole('group', {name: 'Add a table'});
    expect(within(addGroup).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '+ Search Table',
      '+ AI Search Table',
    ]);
    expect(within(section).getByText('Help: buttons, saving and tables')).toBeInTheDocument();
  });

  it('omits the search table number until there are multiple tables', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.queryByRole('button', {name: /delete table/i})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: /\+ search table/i}));

    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 1'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 2'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /delete table: search table 1/i})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /delete table: search table 2/i})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /delete table: search table 1/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 2'})).toBeNull();
    expect(screen.queryByRole('button', {name: /delete table/i})).toBeNull();
  });

  it('does not number the only standard Search Table when an AI Search Table is also open', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
  });

  it('ignores a rows change when no refresh was requested', () => {
    const onRefreshRows = vi.fn();
    const {rerender} = render(
      <PastProjectsBuilder
        rows={ROWS}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    rerender(
      <PastProjectsBuilder
        rows={[...ROWS, makeRow({team_number: 'T04', team_name: 'Team Delta', project_title: 'Delta Project'})]}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    expect(onRefreshRows).not.toHaveBeenCalled();
    expect(screen.queryByText('Delta Project')).toBeNull();
  });

  it('navigates to login when the sign-in dialog is confirmed', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: 'AI Search Table'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: /sign in/i}));

    expect(mockBuildLoginPath).toHaveBeenCalled();
  });
});
