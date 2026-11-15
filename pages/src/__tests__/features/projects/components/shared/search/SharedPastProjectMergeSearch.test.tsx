import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
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
    fireEvent.click(screen.getByRole('button', {name: 'Try Again'}));
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
});
