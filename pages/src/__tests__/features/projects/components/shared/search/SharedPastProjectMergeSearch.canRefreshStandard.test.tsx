import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {SharedPastProjectMergeSearch} from '@/features/projects/components/shared/search/SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {alphaRow, bravoRow, charlieRow, makeRow} from '@/__tests__/features/projects/components/shared/search/sharedPastProjectMergeSearchFixtures';

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

  it('can refresh a standard search table without deleting it', () => {
    const onRefreshRows = vi.fn();
    const onAddRows = vi.fn();

    const {rerender} = render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={onAddRows}
        onRefreshRows={onRefreshRows}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /refresh search table/i}));

    expect(onRefreshRows).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    // Without a catalog in context it words itself as Past Projects does.
    expect(screen.getByText('Refreshing this search table from the latest past-project archive…')).toBeInTheDocument();

    // The refetch resolves with a new archive snapshot; the table picks up the new project.
    const deltaRow = makeRow({team_number: 'T04', team_name: 'Team Delta', project_title: 'Delta Project'});
    rerender(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow, deltaRow]}
        onAddRows={onAddRows}
        onRefreshRows={onRefreshRows}
      />,
    );

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.getAllByText('Delta Project').length).toBeGreaterThan(0);
    expect(screen.getByText('Search table refreshed from the latest past-project archive.')).toBeInTheDocument();
  });

  it('words its search and refresh after All Projects, the list the share page gives it', () => {
    const props = {currentRows: [alphaRow], error: null, loading: false, onAddRows: vi.fn(), onRefreshRows: vi.fn()};
    const search = (rows: ProjectGridRow[]) => (
      <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>
        <SharedPastProjectMergeSearch rows={rows} {...props} />
      </ProjectCatalogContext.Provider>
    );
    const {rerender} = render(search([alphaRow, bravoRow]));

    expect(screen.getByRole('heading', {level: 2, name: 'Add More Projects'})).toBeInTheDocument();
    expect(screen.getByText('Search for more projects to add to this curation.')).toBeInTheDocument();
    expect(screen.queryByText(/archive/)).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: /refresh search table/i}));
    expect(screen.getByText('Refreshing this search table from the latest project list…')).toBeInTheDocument();

    rerender(search([alphaRow, bravoRow, charlieRow]));
    expect(screen.getByText('Search table refreshed from the latest project list.')).toBeInTheDocument();
  });

  it('adds a second standard search table with numbered titles', () => {
    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /\+ search table/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 1'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 2'})).toBeInTheDocument();
  });

  it('removes a search table', () => {
    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /\+ search table/i}));
    fireEvent.click(screen.getByRole('button', {name: /delete table: search table 1/i}));

    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
  });

  it('does not add a project that has just become part of the shared result', async () => {
    const onAddRows = vi.fn();
    const {rerender} = render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow]}
        onAddRows={onAddRows}
      />,
    );

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);

    // Bravo joins the shared result before the pending merge is submitted.
    rerender(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow, bravoRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow]}
        onAddRows={onAddRows}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    await waitFor(() =>
      expect(tableStatus()).toHaveTextContent('That project is already in this curation.'),
    );
    expect(onAddRows).not.toHaveBeenCalled();
  });
});
