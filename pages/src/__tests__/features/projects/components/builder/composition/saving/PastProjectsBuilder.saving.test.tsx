import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {authenticatedAuth, getMergedSection, makeRow, ROWS} from '@/__tests__/features/projects/components/builder/composition/fixtures/pastProjectsBuilderFixtures';

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

// The first search table's save announcer (the page and the draft card have status lines of their own).
const tableStatus = () =>
  within(screen.getAllByRole('heading', {level: 3, name: /search table/i})[0].closest('[data-search-table-id]') as HTMLElement).getByRole(
    'status',
  );

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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', {name: /clear draft/i}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: /clear the curation draft/i})).getByRole('button', {
        name: /clear draft/i,
      }),
    );

    expect(within(getMergedSection() as HTMLElement).queryByText('Bravo Project')).toBeNull();
    expect(screen.getByText(/Curation draft cleared/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /^undo$/i}));
    expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(screen.getByText('Curation draft restored.')).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

    await waitFor(() => expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalled());
    await waitFor(() =>
      expect(tableStatus()).toHaveTextContent('1 project added to the curation draft (1 in total).'),
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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    const saving = screen.getByRole('button', {name: 'Adding…'});
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
      fireEvent.click(within(table(name)).getByRole('button', {name: /add to curation/i}));
    }
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(2);

    await act(async () => { resolvers[0]({rows: [hydrated], failedIndexes: [], unavailableIndexes: []}); });
    await act(async () => { resolvers[1]({rows: [hydrated], failedIndexes: [], unavailableIndexes: []}); });

    const persisted = (storedDraft()?.rows ?? []);
    expect(persisted).toHaveLength(1);
    expect(within(table('Search Table 1')).getByRole('status')).toHaveTextContent(
      '1 project added to the curation draft (1 in total).',
    );
    // The later save reports against what was committed meanwhile, not what it saw when clicked.
    expect(within(table('Search Table 2')).getByRole('status')).toHaveTextContent(
      'That project is already in the curation draft.',
    );
  });

  it('explains a failed detail load instead of silently saving nothing', async () => {
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [compact], failedIndexes: [0], unavailableIndexes: []});

    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '1 project could not be loaded and is still selected. Click Add to Curation to try again.',
    );
    expect(getMergedSection()).toBeNull();
    expect(screen.getAllByLabelText('Select Id Only')[0]).toBeChecked();
  });
});
