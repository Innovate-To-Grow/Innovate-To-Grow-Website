import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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

describe('PastProjectsBuilder — saving into the merged results', () => {
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

  // The draft (saved projects, name and note) is kept in localStorage: the login button reloads the page, and a
  // visitor who closes the tab must find the curation they were building when they come back.
  const DRAFT_STORAGE_KEY = 'past-projects:builder:draft';

  const storedDraft = () => {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as {owner: string | null; rows: ProjectGridRow[]; name: string; note: string}) : null;
  };

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
    const persisted = (storedDraft()?.rows ?? []);
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

    const persisted = (storedDraft()?.rows ?? []);
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
    const shareButtons = screen.getAllByRole('button', {name: /save curation/i});
    shareButtons.forEach((button) => expect(button).toBeDisabled());
    expect(screen.getByText(/Waiting for projects to finish saving/)).toBeInTheDocument();

    await act(async () => resolveDetails({rows: [{...compact, abstract: 'Loaded'}], failedIndexes: [], unavailableIndexes: []}));
    screen.getAllByRole('button', {name: /save curation/i}).forEach((button) => expect(button).toBeEnabled());
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

    const persisted = (storedDraft()?.rows ?? []);
    expect(persisted.map((row) => [row.project_title, row.abstract])).toEqual([['Saved Later', 'Later abstract']]);
    expect(within(searchTable).getByRole('status')).toHaveTextContent(
      '1 project added to Saved Merged Results (1 in total). ' +
        '1 project was removed from Saved Merged Results while saving and is still selected.',
    );
    // Still checked, so it can be saved again.
    expect(within(searchTable).getAllByLabelText('Select Saved First')[0]).toBeChecked();
    expect(within(searchTable).getAllByLabelText('Select Saved Later')[0]).not.toBeChecked();
  });

  it('keeps reporting a save in its table when a refresh lands while it runs', async () => {
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
    expect(screen.getByText('Search table refreshed from the latest past-project archive.')).toBeInTheDocument();
    // The table was reset in place, so the save is still shown as running there.
    expect(screen.getByRole('button', {name: 'Saving…'})).toBeInTheDocument();

    await act(async () => resolveDetails({rows: [compact], failedIndexes: [0], unavailableIndexes: []}));

    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    expect(within(searchTable).getByRole('alert')).toHaveTextContent(
      '1 project could not be loaded and is still selected. Click Save Selected to try again.',
    );
    expect(within(searchTable).getAllByLabelText('Select Id Only')[0]).toBeChecked();
  });

  it('waits for the curation being saved before saving more projects', async () => {
    let finishShare!: (value: string) => void;
    const onCreateShare = vi.fn(() => new Promise<string>((resolve) => { finishShare = resolve; }));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);
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

    it('keeps the field the user is typing in where it is when the saved list grows above it', () => {
      const nameTops = [100, 186];
      vi.mocked(Element.prototype.getBoundingClientRect).mockImplementation(function (this: Element) {
        const top = this.matches('input[type="text"]')
          ? (nameTops.shift() ?? 186)
          : this.hasAttribute('data-search-table-id')
            ? (tops.shift() ?? 300)
            : 0;
        return {top, bottom: top + 40, left: 0, right: 0, width: 0, height: 40, x: 0, y: top, toJSON: () => ({})} as DOMRect;
      });
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
      fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
      scrollBy.mockReset();

      screen.getByLabelText(/curation name/i).focus();
      fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));

      expect(getMergedSection()?.textContent).toContain('Bravo Project');
      expect(scrollBy).toHaveBeenCalledWith(0, 86);
    });

    it('leaves the page alone while the user is working in the saved results and nothing moves', () => {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
      fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /save selected/i}));
      scrollBy.mockReset();

      screen.getByLabelText(/curation name/i).focus();
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
});
