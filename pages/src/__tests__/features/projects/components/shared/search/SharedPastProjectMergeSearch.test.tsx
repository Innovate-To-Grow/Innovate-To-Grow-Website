import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {SharedPastProjectMergeSearch} from '@/features/projects/components/shared/search/SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

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

// The first search table's save announcer (the page has a status line of its own).
const tableStatus = () =>
  within(screen.getAllByRole('heading', {level: 3, name: /search table/i})[0].closest('[data-search-table-id]') as HTMLElement).getByRole(
    'status',
  );

const alphaRow = makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'});
const bravoRow = makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'});
const charlieRow = makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'});

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

  it('announces that the archive is loading', () => {
    render(<SharedPastProjectMergeSearch currentRows={[alphaRow]} rows={[]} error={null} loading onAddRows={vi.fn()} />);

    expect(screen.getByText('Loading past projects…').closest('[role="status"]')).not.toBeNull();
  });

  it('keeps reporting an add in its table when a refresh lands while it runs', async () => {
    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValue(new Promise((resolve) => { resolveDetails = resolve; }));
    const compact = makeRow({id: 'p-9', team_number: 'T09', project_title: 'Id Only'});
    const onAddRows = vi.fn().mockResolvedValue(undefined);
    const props = {currentRows: [alphaRow], error: null, loading: false, onAddRows, onRefreshRows: vi.fn()};
    const {rerender} = render(<SharedPastProjectMergeSearch rows={[compact]} {...props} />);

    fireEvent.click(screen.getByRole('button', {name: 'Refresh Search Table'}));
    fireEvent.click(screen.getAllByLabelText('Select Id Only')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
    rerender(<SharedPastProjectMergeSearch rows={[{...compact}]} {...props} />);

    await act(async () => resolveDetails({rows: [compact], failedIndexes: [0], unavailableIndexes: []}));

    expect(screen.getByRole('alert')).toHaveTextContent(
      '1 project could not be loaded and is still selected. Click Add to Curation to try again.',
    );
    expect(screen.getAllByLabelText('Select Id Only')[0]).toBeChecked();
    expect(onAddRows).not.toHaveBeenCalled();
  });

  it('keeps its table when a refresh fails, and offers to try again when the first load fails', () => {
    const onRefreshRows = vi.fn();
    const props = {currentRows: [alphaRow], loading: false, onAddRows: vi.fn(), onRefreshRows};
    // A failed refetch keeps serving the same rows array.
    const archive = [bravoRow];
    const {rerender} = render(<SharedPastProjectMergeSearch rows={archive} error={null} {...props} />);
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Refresh Search Table'}));
    rerender(<SharedPastProjectMergeSearch rows={archive} error="Network Error" {...props} />);

    expect(screen.getAllByLabelText('Select Bravo Project')[0]).toBeChecked();
    expect(screen.getByRole('alert')).toHaveTextContent(/This table was not refreshed/);
    expect(screen.queryByText('Network Error')).toBeNull();

    cleanup();
    render(<SharedPastProjectMergeSearch rows={[]} error="Network Error" {...props} />);
    fireEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(onRefreshRows).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('Network Error')).toBeNull();
  });

  it('uses the search table merge flow to add selected projects', async () => {
    const onAddRows = vi.fn().mockResolvedValue(undefined);

    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={onAddRows}
      />,
    );

    expect(screen.getByRole('heading', {level: 2, name: 'Add More Projects'})).toBeInTheDocument();
    expect(screen.getByText('Help: Buttons, Saving and Tables')).toBeInTheDocument();
    expect(screen.getAllByRole('button', {name: 'Add to Curation'}).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByText('Alpha Project')).toBeNull();
    expect(screen.getAllByText('Bravo Project').length).toBeGreaterThan(0);

    // The per-table merge button adds the checked rows directly — there is no confirmation dialog.
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    await waitFor(() => {
      expect(onAddRows).toHaveBeenCalledWith([
        expect.objectContaining({
          project_title: 'Bravo Project',
          semester_label: '2025 Spring',
        }),
      ]);
    });
    await waitFor(() => expect(tableStatus()).toHaveTextContent('1 project added.'));
  });

  // Archive rows arrive compact. Saving them unchanged wrote the abstract and student names
  // away as blank for every viewer of the share, and the detail endpoint is the only place
  // that content exists.
  it('fills in missing abstracts and student names before adding archive rows', async () => {
    const compact = makeRow({id: 'p-1', team_number: 'T50', project_title: 'Compact Project'});
    const hydrated = {...compact, abstract: 'Real abstract', student_names: 'Ada, Alan'};
    mockHydrateProjectGridRowsSettled.mockResolvedValue({rows: [hydrated], failedIndexes: [], unavailableIndexes: []});
    const onAddRows = vi.fn().mockResolvedValue(undefined);

    render(
      <SharedPastProjectMergeSearch currentRows={[]} error={null} loading={false}
        rows={[compact]} onAddRows={onAddRows} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Compact Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    await waitFor(() => expect(onAddRows).toHaveBeenCalled());
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalled();
    expect(onAddRows).toHaveBeenCalledWith([
      expect.objectContaining({abstract: 'Real abstract', student_names: 'Ada, Alan'}),
    ]);
  });

  it('does not offer a project whose hydrated copy is already in the shared result', () => {
    const compact = makeRow({id: 'p-1', team_number: 'T50', project_title: 'Compact Project'});
    const sharedCopy = {...compact, abstract: 'Real abstract', student_names: 'Ada, Alan'};

    render(
      <SharedPastProjectMergeSearch currentRows={[sharedCopy]} error={null} loading={false}
        rows={[compact]} onAddRows={vi.fn()} />,
    );

    // The content fingerprint differs, but it is the same project id.
    expect(screen.queryByText('Compact Project')).toBeNull();
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

  it('keeps the selection and shows an error when adding projects fails', async () => {
    const onAddRows = vi.fn().mockRejectedValue(new Error('boom'));

    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow]}
        onAddRows={onAddRows}
      />,
    );

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to add selected projects. They are still selected, so you can try again.',
    );
    expect(screen.getAllByLabelText('Select Bravo Project')[0]).toBeChecked();
  });

  it('ignores a rows change when no refresh was requested', () => {
    const {rerender} = render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow]}
        onAddRows={vi.fn()}
      />,
    );

    rerender(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    expect(screen.queryByText('Charlie Project')).toBeNull();
  });
});
