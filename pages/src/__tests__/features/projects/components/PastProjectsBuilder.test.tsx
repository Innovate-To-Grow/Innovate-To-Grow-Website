import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';
import type {ProjectTableRow} from '@/features/projects/api';

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

const makeProjectTableRow = (overrides: Partial<ProjectTableRow>): ProjectTableRow => ({
  id: 'project-1',
  semester_label: '2024-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Solar Team',
  project_title: 'Solar Project',
  organization: 'Solar Org',
  industry: 'Energy',
  abstract: 'A solar project abstract.',
  student_names: 'Alex Student',
  track: null,
  presentation_order: null,
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
    // The builder persists merged rows to sessionStorage; clear it so drafts don't leak between tests.
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

  it('omits the search table number until there are multiple tables', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.queryByRole('button', {name: /delete search table/i})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: /\+ search table/i}));

    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 1'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 2'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /delete search table 1/i})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /delete search table 2/i})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /delete search table 1/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 2'})).toBeNull();
    expect(screen.queryByRole('button', {name: /delete search table/i})).toBeNull();
  });

  it('does not number the only standard Search Table when an AI Search Table is also open', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
  });

  it('adds AI results as a selectable AI Search Table and merges checked rows', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'solar sensors',
      results: [
        makeProjectTableRow({
          id: 'ai-project-1',
          project_title: 'Solar Sensor Platform',
          team_number: '201',
        }),
      ],
      usage: {inputTokens: 10, outputTokens: 2, totalTokens: 12},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
    const aiSearchInput = screen.getByPlaceholderText(/ask ai to find relevant past projects/i);
    expect(aiSearchInput.closest('.project-grid-controls-row')).not.toBeNull();
    expect(aiSearchInput.closest('.past-projects-action-bar')).toBeNull();

    fireEvent.change(aiSearchInput, {
      target: {value: 'solar sensors'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('solar sensors', 10);

    const aiTable = screen
      .getByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})
      .closest('section') as HTMLElement;
    fireEvent.click((await within(aiTable).findAllByLabelText('Select Solar Sensor Platform'))[0]);
    await waitFor(() => expect(within(aiTable).getByRole('button', {name: /save selected/i})).toBeEnabled());
    fireEvent.click(within(aiTable).getByRole('button', {name: /save selected/i}));

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    expect(within(merged as HTMLElement).getAllByText('Solar Sensor Platform').length).toBeGreaterThan(0);
  });

  it('shows AI search progress while the request is running', async () => {
    let resolveSearch: (value: Awaited<ReturnType<typeof mockSearchPastProjectsWithAI>>) => void = () => {};
    mockSearchPastProjectsWithAI.mockReturnValue(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }),
    );

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar sensors'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    const aiSearchForm = screen.getByPlaceholderText(/ask ai to find relevant past projects/i).closest('form');
    const aiSearchInputFrame = screen
      .getByPlaceholderText(/ask ai to find relevant past projects/i)
      .closest('.past-projects-ai-search-input-frame');
    expect(aiSearchForm).toHaveClass('past-projects-ai-search', 'is-loading');
    expect(aiSearchForm).toHaveAttribute('aria-busy', 'true');
    expect(aiSearchInputFrame).not.toBeNull();
    expect(within(aiSearchForm as HTMLElement).getByRole('status')).toHaveTextContent('Searching past projects with AI...');
    expect(document.querySelector('.past-projects-ai-search-spinner')).toBeNull();
    expect(document.querySelector('.past-projects-ai-search-progress')).toBeNull();
    expect(screen.getByText('Searching past projects with AI...').closest('.project-grid-controls-status')).toBeNull();
    expect(screen.getByRole('button', {name: 'Search'})).toBeDisabled();
    expect(screen.queryByText('Searching...')).toBeNull();

    resolveSearch({
      available: true,
      query: 'solar sensors',
      results: [
        makeProjectTableRow({
          id: 'ai-project-1',
          project_title: 'Solar Sensor Platform',
          team_number: '201',
        }),
      ],
      usage: {inputTokens: 10, outputTokens: 2, totalTokens: 12},
    });

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})).toBeInTheDocument();
  });

  it('does not call AI search when the visitor is signed out', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const addAIButton = screen.getByRole('button', {name: /\+ ai search table/i});
    expect(screen.queryByText('Sign in to use AI search.')).toBeNull();
    expect(addAIButton).toBeEnabled();
    expect(addAIButton).not.toHaveAttribute('aria-disabled');
    expect(addAIButton).toHaveClass('is-login-required');
    fireEvent.click(addAIButton);

    expect(screen.getByRole('dialog', {name: /sign in required/i})).toBeInTheDocument();
    expect(screen.getByText('You need to sign in before using AI search.')).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).not.toHaveBeenCalled();
    expect(screen.queryByPlaceholderText(/ask ai to find relevant past projects/i)).toBeNull();
  });

  it('shows unavailable AI search responses inline inside the AI table', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: false,
      message: 'AI search is not configured yet.',
      query: 'solar',
      results: [],
      usage: {},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect((await screen.findByText('AI search is not configured yet.')).closest('.past-projects-ai-search-message')).toHaveClass(
      'past-projects-ai-search-message',
      'is-error',
    );
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
  });

  it('allows only one AI Search Table at a time', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const addAIButton = screen.getByRole('button', {name: /\+ ai search table/i});
    expect(addAIButton).toBeEnabled();

    fireEvent.click(addAIButton);

    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
    expect(addAIButton).toBeDisabled();
    expect(screen.getAllByRole('heading', {level: 3, name: /ai search table/i})).toHaveLength(1);
  });

  // The login button reloads the page (window.location), so the merged results must survive a
  // full reload via sessionStorage — otherwise signing in to share wipes the user's work.
  const MERGED_ROWS_STORAGE_KEY = 'past-projects:builder:merged-rows';

  it('restores merged results persisted before a login reload', () => {
    sessionStorage.setItem(
      MERGED_ROWS_STORAGE_KEY,
      JSON.stringify([makeRow({team_number: 'T09', project_title: 'Persisted Project'})]),
    );

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    expect(within(merged as HTMLElement).getAllByText('Persisted Project').length).toBeGreaterThan(0);
  });

  it('persists merged results to sessionStorage so a login reload can restore them', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull();

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

    const stored = sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY);
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored as string) as Array<{project_title: string}>;
    expect(parsed).toHaveLength(1);
    expect(parsed[0].project_title).toBe('Bravo Project');
  });

  it('can reset merged results and undo the reset', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', {name: /reset merged results/i}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: /reset merged results/i})).getByRole('button', {
        name: /reset merged results/i,
      }),
    );

    expect(within(getMergedSection() as HTMLElement).queryByText('Bravo Project')).toBeNull();
    expect(screen.getByText(/Merged results reset/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /undo merged change/i}));
    expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(screen.getByText('Merged results restored.')).toBeInTheDocument();
  });

  it('clears the persisted draft once a share is created successfully', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/name this curation/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getAllByRole('button', {name: /get shareable url/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull());
  });

  it('keeps the persisted draft when share creation fails', async () => {
    // The whole point of persistence is to not lose the user's merged rows; a failed share
    // (network error, 4xx/5xx) must leave the draft intact so they can retry.
    const onCreateShare = vi.fn().mockRejectedValue(new Error('boom'));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/name this curation/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getAllByRole('button', {name: /get shareable url/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    // Draft retained after the rejection — the clear runs only after a successful await.
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).not.toBeNull();
  });

  it('drops the persisted draft when the user logs out in the same tab', () => {
    // sessionStorage survives a tab session, so without this a second user signing in on a shared
    // machine (tab never closed) would inherit the first user's merged selection.
    mockUseAuth.mockReturnValue(authenticatedAuth);
    sessionStorage.setItem(
      MERGED_ROWS_STORAGE_KEY,
      JSON.stringify([makeRow({team_number: 'T09', project_title: 'Persisted Project'})]),
    );

    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    expect(getMergedSection()).not.toBeNull();

    mockUseAuth.mockReturnValue({isAuthenticated: false});
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull();
    expect(getMergedSection()).toBeNull();
  });

  it('keeps the draft through revalidation and a temporary verification failure', () => {
    const builder = <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />;
    const {rerender} = render(builder);
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    const draft = sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY);

    for (const isInitializing of [true, false]) {
      mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, unverified: true, isInitializing});
      rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBe(draft);
      expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);
    }

    mockUseAuth.mockReturnValue(authenticatedAuth);
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBe(draft);
  });

  it('keeps a guest draft when the guest signs in', () => {
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, user: null});
    sessionStorage.setItem(MERGED_ROWS_STORAGE_KEY, JSON.stringify([ROWS[1]]));
    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    const draft = sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY);
    mockUseAuth.mockReturnValue(authenticatedAuth);
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBe(draft);
    expect(getMergedSection()).not.toBeNull();
  });

  it('clears the draft when switching directly to another member', () => {
    sessionStorage.setItem(MERGED_ROWS_STORAGE_KEY, JSON.stringify([ROWS[1]]));
    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    mockUseAuth.mockReturnValue({...authenticatedAuth, user: {...authenticatedAuth.user, member_uuid: 'member-2'}});
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull();
    expect(getMergedSection()).toBeNull();
  });

  it('clears a restored member draft when initial session verification confirms logout', () => {
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, isInitializing: true, unverified: true});
    sessionStorage.setItem(MERGED_ROWS_STORAGE_KEY, JSON.stringify([ROWS[1]]));
    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    expect(getMergedSection()).not.toBeNull();
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, user: null});
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull();
    expect(getMergedSection()).toBeNull();
  });

  it('does not restore an in-flight merge after a confirmed logout', async () => {
    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValue(
      new Promise((resolve) => { resolveDetails = resolve; }),
    );
    const rows = [makeRow({id: 'pending-project'})];
    const {rerender} = render(
      <PastProjectsBuilder rows={rows} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(1);
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, user: null});
    rerender(<PastProjectsBuilder rows={rows} loading={false} error={null} onCreateShare={vi.fn()} />);
    await act(async () => resolveDetails({rows: [{...rows[0], abstract: 'Loaded details'}], failedIndexes: [], unavailableIndexes: []}));
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull();
    expect(getMergedSection()).toBeNull();
    // The dropped save says so where it was started, and keeps the checkbox for a retry.
    expect(screen.getByRole('alert')).toHaveTextContent('Your sign-in changed while saving, so nothing was saved.');
    expect(screen.getAllByLabelText('Select Alpha Project')[0]).toBeChecked();
  });

  it('shows a no-results message when AI search finds nothing', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'solar',
      results: [],
      usage: {},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI search did not find matching past projects.')).toBeInTheDocument();
  });

  it('shows the API detail when an AI search rejects', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({response: {data: {detail: 'AI backend down.'}}});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI backend down.')).toBeInTheDocument();
  });

  it('shows the message field when an AI search rejects without a detail', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({response: {data: {message: 'Try later.'}}});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('Try later.')).toBeInTheDocument();
  });

  it('ignores malformed persisted merged rows', () => {
    sessionStorage.setItem(MERGED_ROWS_STORAGE_KEY, '{not valid json');

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(getMergedSection()).toBeNull();
  });

  it('hydrates id-only rows before merging them', async () => {
    mockHydrateProjectGridRowsSettled.mockResolvedValue({
      rows: [makeRow({id: 'p-9', team_number: 'T09', project_title: 'Hydrated Project'})],
      failedIndexes: [],
      unavailableIndexes: [],
    });
    const rowsWithId = [makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'})];

    render(<PastProjectsBuilder rows={rowsWithId} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

    await waitFor(() => expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('1 project added to Saved Merged Results (1 in total).'),
    );
    expect(within(getMergedSection() as HTMLElement).getAllByText('Hydrated Project').length).toBeGreaterThan(0);
  });

  it('ignores a second click on the same table while its save is still loading', async () => {
    const resolvers: Array<(result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void> = [];
    mockHydrateProjectGridRowsSettled.mockImplementation(
      () => new Promise((resolve) => { resolvers.push(resolve); }),
    );
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    const hydrated = {...compact, abstract: 'Abstract', student_names: 'Ada'};

    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    const saving = screen.getByRole('button', {name: 'Saving…'});
    expect(saving).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(saving);
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(1);

    await act(async () => { resolvers[0]({rows: [hydrated], failedIndexes: [], unavailableIndexes: []}); });
    const persisted = JSON.parse(sessionStorage.getItem('past-projects:builder:merged-rows') ?? '[]');
    expect(persisted).toHaveLength(1);
  });

  it('stores a project once when two tables save it at the same time', async () => {
    const resolvers: Array<(result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void> = [];
    mockHydrateProjectGridRowsSettled.mockImplementation(
      () => new Promise((resolve) => { resolvers.push(resolve); }),
    );
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    const hydrated = {...compact, abstract: 'Abstract', student_names: 'Ada'};

    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table = (name: string) =>
      screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;
    for (const name of ['Search Table 1', 'Search Table 2']) {
      fireEvent.click(within(table(name)).getAllByLabelText('Select Id Only')[0]);
      fireEvent.click(within(table(name)).getByRole('button', {name: /save selected/i}));
    }
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(2);

    await act(async () => { resolvers[0]({rows: [hydrated], failedIndexes: [], unavailableIndexes: []}); });
    await act(async () => { resolvers[1]({rows: [hydrated], failedIndexes: [], unavailableIndexes: []}); });

    const persisted = JSON.parse(sessionStorage.getItem('past-projects:builder:merged-rows') ?? '[]');
    expect(persisted).toHaveLength(1);
    expect(within(table('Search Table 1')).getByRole('status')).toHaveTextContent(
      '1 project added to Saved Merged Results (1 in total).',
    );
    // The later save reports against what was committed meanwhile, not what it saw when clicked.
    expect(within(table('Search Table 2')).getByRole('status')).toHaveTextContent(
      'That project is already in Saved Merged Results.',
    );
  });

  it('explains a failed detail load instead of silently saving nothing', async () => {
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [compact], failedIndexes: [0], unavailableIndexes: []});

    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '1 project could not be loaded and is still selected. Click Save Selected to try again.',
    );
    expect(getMergedSection()).toBeNull();
    expect(screen.getAllByLabelText('Select Id Only')[0]).toBeChecked();
  });

  it('keeps the projects that loaded when only some details fail', async () => {
    const first = makeRow({id: 'p-1', team_number: 'T01', project_title: 'Loads Fine'});
    const second = makeRow({id: 'p-2', team_number: 'T02', project_title: 'Fails To Load'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({
      rows: [{...first, abstract: 'Loaded'}, second],
      failedIndexes: [1],
      unavailableIndexes: [],
    });

    render(<PastProjectsBuilder rows={[first, second]} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getAllByLabelText('Select Loads Fine')[0]);
    fireEvent.click(screen.getAllByLabelText('Select Fails To Load')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '1 project added to Saved Merged Results (1 in total). 1 project could not be loaded and is still selected.',
    );
    const merged = within(getMergedSection() as HTMLElement);
    expect(merged.getAllByText('Loads Fine').length).toBeGreaterThan(0);
    expect(merged.queryByText('Fails To Load')).toBeNull();
    expect(screen.getAllByLabelText('Select Loads Fine')[0]).not.toBeChecked();
    expect(screen.getAllByLabelText('Select Fails To Load')[0]).toBeChecked();
  });

  it('skips merging a project already in the saved results', async () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
    expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);

    // The merged table above also lists Bravo, so target the search table's checkbox.
    fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

    expect(within(searchTable).getByRole('status')).toHaveTextContent('That project is already in Saved Merged Results.');
  });

  it('reports each save inside its table and marks saved projects in every table', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(screen.getByRole('status')).toHaveTextContent('1 project added to Saved Merged Results (1 in total).');
    expect(screen.getByRole('button', {name: 'View Saved Results'})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table2 = screen.getByRole('heading', {level: 3, name: 'Search Table 2'}).closest('section') as HTMLElement;
    // Desktop table + mobile card.
    expect(within(table2).getAllByText('Saved')).toHaveLength(2);
  });

  it('shows newly saved older projects instead of leaving them on a later page', () => {
    const newer = Array.from({length: 5}, (_, index) =>
      makeRow({semester_label: '2026 Spring', team_number: `N${index}`, project_title: `Newer ${index}`}),
    );
    const older = makeRow({semester_label: '2021 Fall', team_number: 'O1', project_title: 'Older Project'});
    render(<PastProjectsBuilder rows={[...newer, older]} loading={false} error={null} onCreateShare={vi.fn()} />);

    newer.forEach((row) => fireEvent.click(screen.getAllByLabelText(`Select ${row.project_title}`)[0]));
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    // The search table pages at 5 rows too; the older project sits on its page 2.
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getByRole('button', {name: 'Next'}));
    fireEvent.click(within(searchTable).getAllByLabelText('Select Older Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

    const merged = getMergedSection() as HTMLElement;
    expect(within(merged).getByText('Page 2 of 2')).toBeInTheDocument();
    const olderRow = within(merged).getAllByText('Older Project')[0].closest('tr') as HTMLElement;
    expect(olderRow).toHaveClass('is-new');
  });

  it('waits for saves still loading before a shareable link can be created', async () => {
    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValue(new Promise((resolve) => { resolveDetails = resolve; }));
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    const onCreateShare = vi.fn();
    render(<PastProjectsBuilder rows={[...ROWS, compact]} loading={false} error={null} onCreateShare={onCreateShare} />);

    // Alpha needs no detail request, so the saved results card appears straight away.
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

    // A link created now would leave out the project that is still loading.
    const shareButtons = screen.getAllByRole('button', {name: /get shareable url/i});
    shareButtons.forEach((button) => expect(button).toBeDisabled());
    expect(screen.getByText(/Waiting for projects to finish saving/)).toBeInTheDocument();

    await act(async () => resolveDetails({rows: [{...compact, abstract: 'Loaded'}], failedIndexes: [], unavailableIndexes: []}));
    screen.getAllByRole('button', {name: /get shareable url/i}).forEach((button) => expect(button).toBeEnabled());
    expect(screen.queryByText(/Waiting for projects to finish saving/)).toBeNull();
  });

  it('points out checked projects another table has not saved yet', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table = (name: string) =>
      screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;

    fireEvent.click(within(table('Search Table 1')).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(table('Search Table 2')).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(table('Search Table 2')).getByRole('button', {name: /save selected/i}));

    expect(within(table('Search Table 2')).getByRole('status')).toHaveTextContent(
      '1 project added to Saved Merged Results (1 in total). Search Table 1 still has 1 selected project that is not saved yet.',
    );
  });

  it('does not load details again for a project that is already saved', async () => {
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({
      rows: [{...compact, abstract: 'Loaded'}],
      failedIndexes: [],
      unavailableIndexes: [],
    });
    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;

    fireEvent.click(within(searchTable).getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
    await waitFor(() => expect(getMergedSection()).not.toBeNull());

    fireEvent.click(within(searchTable).getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(1);
    expect(within(searchTable).getByRole('status')).toHaveTextContent('That project is already in Saved Merged Results.');
  });

  it('skips and unchecks a project the archive no longer has', async () => {
    const compact = makeRow({id: 'gone', team_number: 'T09', project_title: 'Removed Project'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [compact], failedIndexes: [], unavailableIndexes: [0]});
    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Removed Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

    // Retrying could never work, so the row is not left checked.
    expect(await screen.findByRole('alert')).toHaveTextContent('1 project is no longer in the archive and was skipped.');
    expect(screen.getAllByLabelText('Select Removed Project')[0]).not.toBeChecked();
    expect(getMergedSection()).toBeNull();
  });

  it('keeps a Reset undoable when a save lands after it', async () => {
    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValue(new Promise((resolve) => { resolveDetails = resolve; }));
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Late Project'});
    render(<PastProjectsBuilder rows={[...ROWS, compact]} loading={false} error={null} onCreateShare={vi.fn()} />);
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;

    fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
    fireEvent.click(within(searchTable).getAllByLabelText('Select Late Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
    fireEvent.click(screen.getByRole('button', {name: 'Reset Merged Results'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Reset Merged Results'}));

    await act(async () => resolveDetails({rows: [{...compact, abstract: 'Loaded'}], failedIndexes: [], unavailableIndexes: []}));
    fireEvent.click(screen.getByRole('button', {name: 'Undo Merged Change'}));

    const merged = within(getMergedSection() as HTMLElement);
    expect(merged.getAllByText('Alpha Project').length).toBeGreaterThan(0);
    expect(merged.getAllByText('Late Project').length).toBeGreaterThan(0);
  });

  it('keeps the table that saved where it was when the saved results card appears above it', () => {
    const scrollBy = vi.fn();
    vi.stubGlobal('scrollBy', scrollBy);
    const tops = [120, 920];
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      const top = this.hasAttribute('data-search-table-id') ? (tops.shift() ?? 920) : 0;
      return {top, bottom: top, left: 0, right: 0, width: 0, height: 0, x: 0, y: top, toJSON: () => ({})} as DOMRect;
    });
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    try {
      fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

      expect(scrollBy).toHaveBeenCalledWith(0, 800);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('does not put back a copy without details of a saved project removed while a save loads', async () => {
    const first = makeRow({id: 'p-1', team_number: 'T01', project_title: 'Saved First'});
    const later = makeRow({id: 'p-2', team_number: 'T02', project_title: 'Saved Later'});
    mockHydrateProjectGridRowsSettled.mockResolvedValueOnce({
      rows: [{...first, abstract: 'First abstract'}],
      failedIndexes: [],
      unavailableIndexes: [],
    });
    render(<PastProjectsBuilder rows={[first, later]} loading={false} error={null} onCreateShare={vi.fn()} />);
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Saved First')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
    await waitFor(() => expect(getMergedSection()).not.toBeNull());

    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValueOnce(new Promise((resolve) => { resolveDetails = resolve; }));
    fireEvent.click(within(searchTable).getAllByLabelText('Select Saved First')[0]);
    fireEvent.click(within(searchTable).getAllByLabelText('Select Saved Later')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
    // Only the project not saved yet is loaded.
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenLastCalledWith([expect.objectContaining({id: 'p-2'})], expect.anything());
    // The saved project is removed while the other one loads.
    fireEvent.click(screen.getByRole('button', {name: 'Reset Merged Results'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Reset Merged Results'}));

    await act(async () => resolveDetails({rows: [{...later, abstract: 'Later abstract'}], failedIndexes: [], unavailableIndexes: []}));

    const persisted = JSON.parse(sessionStorage.getItem('past-projects:builder:merged-rows') ?? '[]') as ProjectGridRow[];
    expect(persisted.map((row) => [row.project_title, row.abstract])).toEqual([['Saved Later', 'Later abstract']]);
    expect(within(searchTable).getByRole('status')).toHaveTextContent(
      '1 project added to Saved Merged Results (1 in total). 1 project was already saved.',
    );
  });

  it('shows the outcome in the reloaded table when a refresh lands while it saves', async () => {
    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValue(new Promise((resolve) => { resolveDetails = resolve; }));
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    const onRefreshRows = vi.fn();
    const props = {loading: false, error: null, onRefreshRows, onCreateShare: vi.fn()};
    const {rerender} = render(<PastProjectsBuilder rows={[compact]} {...props} />);

    // The archive reload is still running when the save starts, and lands before the save finishes.
    fireEvent.click(screen.getByRole('button', {name: 'Refresh Search Table'}));
    fireEvent.click(screen.getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    rerender(<PastProjectsBuilder rows={[{...compact}]} {...props} />);
    expect(screen.queryByRole('button', {name: 'Saving…'})).toBeNull();

    await act(async () => resolveDetails({rows: [compact], failedIndexes: [0], unavailableIndexes: []}));

    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    expect(within(searchTable).getByRole('alert')).toHaveTextContent(
      'This table was reloaded while saving. 1 project could not be loaded. Select it again and click Save Selected to try again.',
    );
  });

  it('waits for a shareable link being created before saving more projects', async () => {
    let finishShare!: (value: string) => void;
    const onCreateShare = vi.fn(() => new Promise<string>((resolve) => { finishShare = resolve; }));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

    fireEvent.click(screen.getAllByRole('button', {name: /get shareable url/i})[0]);
    expect(onCreateShare).toHaveBeenCalledTimes(1);
    // The link is made from the rows saved at the click, and the draft is dropped once it exists.
    fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
    expect(within(searchTable).getByRole('button', {name: /save selected/i})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Reset Merged Results'})).toBeDisabled();

    await act(async () => finishShare('share-1'));
    expect(within(searchTable).getByRole('button', {name: /save selected/i})).toBeEnabled();
  });

  it('does not call a project unsaved in another table once this save saved it', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table = (name: string) =>
      screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;

    fireEvent.click(within(table('Search Table 2')).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(table('Search Table 1')).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(table('Search Table 1')).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(table('Search Table 1')).getByRole('button', {name: /save selected/i}));

    expect(within(table('Search Table 1')).getByRole('status')).toHaveTextContent(
      /^2 projects added to Saved Merged Results \(2 in total\)\.$/,
    );
  });

  describe('when the saved results change above the search tables', () => {
    let tops: number[];
    const scrollBy = vi.fn();

    beforeEach(() => {
      scrollBy.mockReset();
      vi.stubGlobal('scrollBy', scrollBy);
      tops = [];
      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
        const top = this.hasAttribute('data-search-table-id') ? (tops.shift() ?? 300) : 0;
        return {top, bottom: top + 400, left: 0, right: 0, width: 0, height: 400, x: 0, y: top, toJSON: () => ({})} as DOMRect;
      });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('leaves the page alone while the user is working in the saved results', () => {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
      fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
      scrollBy.mockReset();

      screen.getByLabelText(/name this curation/i).focus();
      tops = [120, 300];
      fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

      expect(getMergedSection()?.textContent).toContain('Bravo Project');
      expect(scrollBy).not.toHaveBeenCalled();
    });

    it('does not pin a table that is off-screen', () => {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      tops = [2000, 2800];
      fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

      expect(getMergedSection()).not.toBeNull();
      expect(scrollBy).not.toHaveBeenCalled();
    });
  });

  it('takes the viewer and keyboard focus to the saved results', () => {
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

      fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
      fireEvent.click(screen.getByRole('button', {name: 'View Saved Results'}));

      expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({block: 'start'}));
      expect(document.activeElement).toBe(screen.getByRole('heading', {level: 2, name: 'Saved Merged Results'}));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('removes multiple selected merged rows at once', async () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    fireEvent.click(screen.getAllByLabelText('Select Charlie Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));

    const merged = getMergedSection() as HTMLElement;
    expect(within(merged).getAllByText('Alpha Project').length).toBeGreaterThan(0);
    expect(within(merged).getAllByText('Charlie Project').length).toBeGreaterThan(0);

    fireEvent.click(within(merged).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(merged).getAllByLabelText('Select Charlie Project')[0]);
    fireEvent.click(within(merged).getByRole('button', {name: /remove selected/i}));

    expect(await screen.findByText('2 projects removed from merged results.')).toBeInTheDocument();
    expect(within(getMergedSection() as HTMLElement).queryByText('Alpha Project')).toBeNull();
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

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: /sign in/i}));

    expect(mockBuildLoginPath).toHaveBeenCalled();
  });
});
