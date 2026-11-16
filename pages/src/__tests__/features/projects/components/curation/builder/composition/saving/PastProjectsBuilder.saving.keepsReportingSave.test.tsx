import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {authenticatedAuth, makeRow, ROWS} from '@/__tests__/features/projects/components/curation/builder/composition/fixtures/pastProjectsBuilderFixtures';

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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    rerender(<PastProjectsBuilder rows={[{...compact}]} {...props} />);
    expect(screen.getByText('Search table refreshed from the latest past-project archive.')).toBeInTheDocument();
    // The table was reset in place, so the save is still shown as running there.
    expect(screen.getByRole('button', {name: 'Adding…'})).toBeInTheDocument();

    await act(async () => resolveDetails({rows: [compact], failedIndexes: [0], unavailableIndexes: []}));

    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    expect(within(searchTable).getByRole('alert')).toHaveTextContent(
      '1 project could not be loaded and is still selected. Click Add to Curation to try again.',
    );
    expect(within(searchTable).getAllByLabelText('Select Id Only')[0]).toBeChecked();
  });

  it('waits for the curation being saved before saving more projects', async () => {
    let finishShare!: (value: string) => void;
    const onCreateShare = vi.fn(() => new Promise<string>((resolve) => { finishShare = resolve; }));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);
    const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);
    expect(onCreateShare).toHaveBeenCalledTimes(1);
    // The link is made from the rows saved at the click, and the draft is dropped once it exists.
    fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
    expect(within(searchTable).getByRole('button', {name: /add to curation/i})).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', {name: 'Clear Draft'})).toHaveAttribute('aria-disabled', 'true');

    await act(async () => finishShare('share-1'));
    expect(within(searchTable).getByRole('button', {name: /add to curation/i})).not.toHaveAttribute('aria-disabled');
  });

  it('does not call a project unsaved in another table once this save saved it', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table = (name: string) =>
      screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;

    fireEvent.click(within(table('Search Table 2')).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(table('Search Table 1')).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(table('Search Table 1')).getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(within(table('Search Table 1')).getByRole('button', {name: /add to curation/i}));

    expect(within(table('Search Table 1')).getByRole('status')).toHaveTextContent(
      /^2 projects added to the curation draft \(2 in total\)\.$/,
    );
  });
});
