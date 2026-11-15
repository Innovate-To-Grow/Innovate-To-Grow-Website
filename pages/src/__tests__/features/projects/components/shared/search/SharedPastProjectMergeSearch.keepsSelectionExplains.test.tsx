import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {SharedPastProjectMergeSearch} from '@/features/projects/components/shared/search/SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {alphaRow, bravoRow, makeRow} from '@/__tests__/features/projects/components/shared/search/sharedPastProjectMergeSearchFixtures';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();
const mockBuildLoginPath = vi.fn();

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

// The first search table's save announcer (the page has a status line of its own).
const tableStatus = () =>
  within(screen.getAllByRole('heading', {level: 3, name: /search table/i})[0].closest('[data-search-table-id]') as HTMLElement).getByRole(
    'status',
  );

describe('SharedPastProjectMergeSearch', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    mockSearchPastProjectsWithAI.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset();
    mockHydrateProjectGridRowsSettled.mockImplementation(async (rows: ProjectGridRow[]) => ({
      rows,
      failedIndexes: [],
      unavailableIndexes: [],
    }));
    mockBuildLoginPath.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('keeps the selection and explains when project details cannot be loaded', async () => {
    const compact = makeRow({id: 'p-1', team_number: 'T50', project_title: 'Compact Project'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [compact], failedIndexes: [0], unavailableIndexes: []});
    const onAddRows = vi.fn();

    render(
      <SharedPastProjectMergeSearch currentRows={[]} error={null} loading={false}
        rows={[compact]} onAddRows={onAddRows} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Compact Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '1 project could not be loaded and is still selected. Click Add to Curation to try again.',
    );
    expect(onAddRows).not.toHaveBeenCalled();
    expect(screen.getAllByLabelText('Select Compact Project')[0]).toBeChecked();
  });

  it('adds the projects that loaded and keeps only the failed ones selected', async () => {
    const first = makeRow({id: 'p-1', team_number: 'T50', project_title: 'Loads Fine'});
    const second = makeRow({id: 'p-2', team_number: 'T51', project_title: 'Fails To Load'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({
      rows: [{...first, abstract: 'Loaded'}, second],
      failedIndexes: [1],
      unavailableIndexes: [],
    });
    const onAddRows = vi.fn().mockResolvedValue(undefined);

    render(
      <SharedPastProjectMergeSearch currentRows={[]} error={null} loading={false}
        rows={[first, second]} onAddRows={onAddRows} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Loads Fine')[0]);
    fireEvent.click(screen.getAllByLabelText('Select Fails To Load')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    expect(await screen.findByRole('alert')).toHaveTextContent('1 project added. 1 project could not be loaded');
    expect(onAddRows).toHaveBeenCalledWith([expect.objectContaining({project_title: 'Loads Fine', abstract: 'Loaded'})]);
    expect(screen.getAllByLabelText('Select Loads Fine')[0]).not.toBeChecked();
    expect(screen.getAllByLabelText('Select Fails To Load')[0]).toBeChecked();
  });

  it('refuses an add that would pass the 1000-project limit before loading anything', async () => {
    const current = Array.from({length: 999}, (_, index) => makeRow({team_number: `C${index}`, project_title: `Current ${index}`}));
    const first = makeRow({id: 'p-1', team_number: 'T50', project_title: 'New One'});
    const second = makeRow({id: 'p-2', team_number: 'T51', project_title: 'New Two'});
    const onAddRows = vi.fn();

    render(
      <SharedPastProjectMergeSearch currentRows={current} error={null} loading={false}
        rows={[first, second]} onAddRows={onAddRows} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select New One')[0]);
    fireEvent.click(screen.getAllByLabelText('Select New Two')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    expect(await screen.findByRole('alert')).toHaveTextContent('A curation can include at most 1000 projects.');
    expect(mockHydrateProjectGridRowsSettled).not.toHaveBeenCalled();
    expect(onAddRows).not.toHaveBeenCalled();
    expect(screen.getAllByLabelText('Select New One')[0]).toBeChecked();
  });

  it('skips and unchecks a project the archive no longer has', async () => {
    const compact = makeRow({id: 'gone', team_number: 'T50', project_title: 'Removed Project'});
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [compact], failedIndexes: [], unavailableIndexes: [0]});
    const onAddRows = vi.fn();

    render(
      <SharedPastProjectMergeSearch currentRows={[]} error={null} loading={false}
        rows={[compact]} onAddRows={onAddRows} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Removed Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    expect(await screen.findByRole('alert')).toHaveTextContent('1 project is no longer in the archive and was skipped.');
    expect(onAddRows).not.toHaveBeenCalled();
    expect(screen.getAllByLabelText('Select Removed Project')[0]).not.toBeChecked();
  });

  it('reports what the share actually appended', async () => {
    // The share already had the project by the time the add was applied.
    const onAddRows = vi.fn().mockResolvedValue(0);

    render(
      <SharedPastProjectMergeSearch currentRows={[alphaRow]} error={null} loading={false}
        rows={[alphaRow, bravoRow]} onAddRows={onAddRows} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    await waitFor(() =>
      expect(tableStatus()).toHaveTextContent('That project is already in this curation.'),
    );
  });
});
