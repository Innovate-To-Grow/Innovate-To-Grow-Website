import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import {authenticatedAuth, getMergedSection, makeRow, ROWS} from '@/__tests__/features/projects/components/curation/builder/composition/fixtures/pastProjectsBuilderFixtures';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/navigation/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/navigation/redirects')>();
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

    // Check exactly one row, then Add to Curation — the per-table merge button. (The grid renders a
    // desktop table and mobile cards, so each row's checkbox/label appears twice — target the first
    // match; both checkboxes map to the same row key.) There is no confirmation dialog anymore.
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    expect(window.confirm).not.toHaveBeenCalled();

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    const mergedView = within(merged as HTMLElement);
    // Only the selected project is saved.
    expect(mergedView.getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(mergedView.queryByText('Alpha Project')).toBeNull();
    expect(mergedView.queryByText('Charlie Project')).toBeNull();
  });

  it('disables Add to Curation until a row is selected and never merges everything by default', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /add to curation/i});
    expect(mergeButton).toHaveAttribute('aria-disabled', 'true');

    // Selecting a row enables it.
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    expect(mergeButton).not.toHaveAttribute('aria-disabled');
  });

  it('does not toggle selection from desktop row body clicks', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /add to curation/i});
    fireEvent.click(screen.getAllByText('Bravo Project')[0]);
    expect(mergeButton).toHaveAttribute('aria-disabled', 'true');

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    expect(mergeButton).not.toHaveAttribute('aria-disabled');
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
    expect(undoButton).toHaveAttribute('aria-disabled', 'true');

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /remove from table/i}));

    expect(screen.queryByText('Bravo Project')).toBeNull();
    expect(undoButton).not.toHaveAttribute('aria-disabled');

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
});
