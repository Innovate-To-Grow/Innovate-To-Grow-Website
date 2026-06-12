import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '../PastProjectsBuilder';
import type {ProjectGridRow} from '../projectGrid';
import type {ProjectTableRow} from '@/features/projects/api';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
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
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    mockSearchPastProjectsWithAI.mockReset();
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

    // Check exactly one row, then Save/Merge. (The grid renders a desktop table
    // and mobile cards, so each row's checkbox/label appears twice — target the
    // first match; both checkboxes map to the same row key.)
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));

    const dialog = screen.getByRole('dialog', {name: /save selected rows/i});
    expect(window.confirm).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', {name: /save rows/i}));

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    const mergedView = within(merged as HTMLElement);
    // Only the selected project is saved.
    expect(mergedView.getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(mergedView.queryByText('Alpha Project')).toBeNull();
    expect(mergedView.queryByText('Charlie Project')).toBeNull();
  });

  it('disables Save/Merge until a row is selected and never merges everything by default', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /save\/merge results/i});
    expect(mergeButton).toBeDisabled();

    // Selecting a row enables it.
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    expect(mergeButton).toBeEnabled();
  });

  it('does not toggle selection from desktop row body clicks', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /save\/merge results/i});
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
    fireEvent.click(screen.getByRole('button', {name: /delete selected rows/i}));

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
    fireEvent.click(screen.getByRole('button', {name: /delete selected rows/i}));
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

    fireEvent.click((await screen.findAllByLabelText('Select Solar Sensor Platform'))[0]);
    await waitFor(() => expect(screen.getByRole('button', {name: /save\/merge results/i})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));

    const dialog = screen.getByRole('dialog', {name: /save selected rows/i});
    fireEvent.click(within(dialog).getByRole('button', {name: /save rows/i}));

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
    expect(screen.getByRole('status')).toHaveTextContent('Searching past projects with AI...');
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
    expect(addAIButton).toHaveAttribute('aria-disabled', 'true');
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
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: /save selected rows/i})).getByRole('button', {name: /save rows/i}),
    );

    const stored = sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY);
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored as string) as Array<{project_title: string}>;
    expect(parsed).toHaveLength(1);
    expect(parsed[0].project_title).toBe('Bravo Project');
  });

  it('can reset merged results and undo the reset', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: /save selected rows/i})).getByRole('button', {name: /save rows/i}),
    );
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
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: /save selected rows/i})).getByRole('button', {name: /save rows/i}),
    );
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).toBeNull());
  });

  it('keeps the persisted draft when share creation fails', async () => {
    // The whole point of persistence is to not lose the user's merged rows; a failed share
    // (network error, 4xx/5xx) must leave the draft intact so they can retry.
    const onCreateShare = vi.fn().mockRejectedValue(new Error('boom'));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: /save selected rows/i})).getByRole('button', {name: /save rows/i}),
    );
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    // Draft retained after the rejection — the clear runs only after a successful await.
    expect(sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY)).not.toBeNull();
  });

  it('drops the persisted draft when the user logs out in the same tab', () => {
    // sessionStorage survives a tab session, so without this a second user signing in on a shared
    // machine (tab never closed) would inherit the first user's merged selection.
    mockUseAuth.mockReturnValue({isAuthenticated: true});
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
});
