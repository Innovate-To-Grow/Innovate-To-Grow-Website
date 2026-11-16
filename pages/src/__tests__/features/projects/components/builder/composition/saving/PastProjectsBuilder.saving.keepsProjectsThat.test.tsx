import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '1 project added to the curation draft (1 in total). 1 project could not be loaded and is still selected.',
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
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
    expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);

    // The merged table above also lists Bravo, so target the search table's checkbox.
    fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

    expect(within(searchTable).getByRole('status')).toHaveTextContent('That project is already in the curation draft.');
  });

  it('reports each save inside its table and marks saved projects in every table', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    expect(tableStatus()).toHaveTextContent('1 project added to the curation draft (1 in total).');
    expect(screen.getByRole('button', {name: 'View Curation Draft'})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table2 = screen.getByRole('heading', {level: 3, name: 'Search Table 2'}).closest('section') as HTMLElement;
    // Only the viewport's layout renders (the desktop table here), so the mark appears once.
    expect(within(table2).getAllByText('Added')).toHaveLength(1);
  });

  it('shows newly saved older projects instead of leaving them on a later page', () => {
    const newer = Array.from({length: 5}, (_, index) =>
      makeRow({semester_label: '2026 Spring', team_number: `N${index}`, project_title: `Newer ${index}`}),
    );
    const older = makeRow({semester_label: '2021 Fall', team_number: 'O1', project_title: 'Older Project'});
    render(<PastProjectsBuilder rows={[...newer, older]} loading={false} error={null} onCreateShare={vi.fn()} />);

    newer.forEach((row) => fireEvent.click(screen.getAllByLabelText(`Select ${row.project_title}`)[0]));
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    // The search table pages at 5 rows too; the older project sits on its page 2.
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getByRole('button', {name: 'Next'}));
    fireEvent.click(within(searchTable).getAllByLabelText('Select Older Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

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
    fireEvent.click(within(table('Search Table 2')).getByRole('button', {name: /add to curation/i}));

    expect(within(table('Search Table 2')).getByRole('status')).toHaveTextContent(
      '1 project added to the curation draft (1 in total). Search Table 1 still has 1 selected project that is not saved yet.',
    );
  });
});
