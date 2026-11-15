import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
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
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
    await waitFor(() => expect(getMergedSection()).not.toBeNull());

    fireEvent.click(within(searchTable).getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(1);
    expect(within(searchTable).getByRole('status')).toHaveTextContent('That project is already in the curation draft.');
  });

  it('skips and unchecks a project the archive no longer has', async () => {
    const compact = makeRow({id: 'gone', team_number: 'T09', project_title: 'Removed Project'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [compact], failedIndexes: [], unavailableIndexes: [0]});
    render(<PastProjectsBuilder rows={[compact]} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Removed Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

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
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
    fireEvent.click(within(searchTable).getAllByLabelText('Select Late Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
    fireEvent.click(screen.getByRole('button', {name: 'Clear Draft'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Clear Draft'}));

    await act(async () => resolveDetails({rows: [{...compact, abstract: 'Loaded'}], failedIndexes: [], unavailableIndexes: []}));
    fireEvent.click(screen.getByRole('button', {name: 'Undo'}));

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
      fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

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
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
    await waitFor(() => expect(getMergedSection()).not.toBeNull());

    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValueOnce(new Promise((resolve) => { resolveDetails = resolve; }));
    fireEvent.click(within(searchTable).getAllByLabelText('Select Saved First')[0]);
    fireEvent.click(within(searchTable).getAllByLabelText('Select Saved Later')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
    // Only the project not saved yet is loaded.
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenLastCalledWith([expect.objectContaining({id: 'p-2'})], expect.anything());
    // The saved project is removed while the other one loads.
    fireEvent.click(screen.getByRole('button', {name: 'Clear Draft'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Clear Draft'}));

    await act(async () => resolveDetails({rows: [{...later, abstract: 'Later abstract'}], failedIndexes: [], unavailableIndexes: []}));

    const persisted = (storedDraft()?.rows ?? []);
    expect(persisted.map((row) => [row.project_title, row.abstract])).toEqual([['Saved Later', 'Later abstract']]);
    expect(within(searchTable).getByRole('status')).toHaveTextContent(
      '1 project added to the curation draft (1 in total). ' +
        '1 project was removed from the curation draft while adding and is still selected.',
    );
    // Still checked, so it can be saved again.
    expect(within(searchTable).getAllByLabelText('Select Saved First')[0]).toBeChecked();
    expect(within(searchTable).getAllByLabelText('Select Saved Later')[0]).not.toBeChecked();
  });
});
