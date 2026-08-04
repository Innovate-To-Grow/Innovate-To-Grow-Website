import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router';

import {PastProjectsPage} from '../PastProjectsPage';
import {
  createPastProjectShare,
  fetchPastProjectShare,
  updatePastProjectShare,
  type PastProjectShare,
  type ProjectGridRow,
} from '@/features/projects/api';

const {
  addedRow,
  mockNavigate,
  sampleRow,
  sharedState,
} = vi.hoisted(() => {
  const sample = {
    id: '11111111-1111-4111-8111-111111111111',
    semester_label: '2025 Spring',
    class_code: 'CAP',
    team_number: '101',
    team_name: 'Team Alpha',
    project_title: 'Shared Project',
    organization: 'Acme',
    industry: 'Technology',
    abstract: 'A detailed project abstract.',
    student_names: 'Alice, Bob',
    is_presenting: '',
  };
  return {
    sampleRow: sample,
    addedRow: {
      ...sample,
      id: '22222222-2222-4222-8222-222222222222',
      team_number: '202',
      team_name: 'Team Beta',
      project_title: 'Queued Project',
    },
    mockNavigate: vi.fn(),
    sharedState: {share: null as unknown},
  };
});

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => {
      const current = sharedState.share as {id?: unknown} | null;
      return {
        shareId:
          typeof current?.id === 'string' ? current.id : undefined,
      };
    },
  };
});

vi.mock('@/features/projects/api', () => ({
  createPastProjectShare: vi.fn(),
  fetchPastProjectShare: vi.fn(),
  updatePastProjectShare: vi.fn(),
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
  usePastProjectGridData: () => ({
    error: null,
    loading: false,
    rows: [sampleRow],
    refetch: vi.fn(),
  }),
  usePastProjectShareData: () => ({
    error: null,
    loading: false,
    share: sharedState.share,
  }),
}));

vi.mock('@/features/projects', () => ({
  createProjectGridItems: (rows: Array<typeof sampleRow>) =>
    rows.map((row, index) => ({...row, __key: `row-${index}`})),
  MergedResultsTable: ({
    note,
    onUpdateShare,
    rows,
    title,
  }: {
    note?: string;
    onUpdateShare?: (
      rows: ProjectGridRow[],
      name: string,
      note: string,
    ) => Promise<void>;
    rows: Array<ProjectGridRow & {__key: string}>;
    title: string;
  }) => {
    const cleanRows = rows.map(({__key, ...row}) => {
      void __key;
      return row;
    });
    return (
      <div>
        <div data-testid="share-note">{note}</div>
        <button
          type="button"
          onClick={() =>
            void onUpdateShare?.(
              cleanRows,
              title,
              'Updated note',
            ).catch(() => undefined)
          }
        >
          Update mocked note
        </button>
        <button
          type="button"
          onClick={() =>
            void onUpdateShare?.(
              cleanRows.map((row, index) =>
                index === 0
                  ? {...row, team_name: 'Edited Team Alpha'}
                  : row,
              ),
              title,
              note ?? '',
            ).catch(() => undefined)
          }
        >
          Edit mocked row
        </button>
      </div>
    );
  },
  SharedPastProjectMergeSearch: ({
    onAddRows,
  }: {
    onAddRows: (rows: ProjectGridRow[]) => Promise<void>;
  }) => (
    <button
      type="button"
      onClick={() => void onAddRows([addedRow]).catch(() => undefined)}
    >
      Add mocked row
    </button>
  ),
  PastProjectsBuilder: ({
    onCreateShare,
  }: {
    onCreateShare: (
      rows: ProjectGridRow[],
      name: string,
      note: string,
    ) => Promise<unknown>;
  }) => (
    <button
      type="button"
      onClick={() =>
        void onCreateShare(
          [sampleRow],
          'Spring finalists',
          'Review note',
        )
      }
    >
      Create mocked share
    </button>
  ),
}));

const shareFixture = (
  overrides: Partial<PastProjectShare> = {},
): PastProjectShare => ({
  id: 'share-abc',
  name: 'Spring finalists',
  rows: [sampleRow],
  note: 'Original note',
  details_text: '<strong>Details</strong>',
  version: 4,
  share_url: '/past-projects/share-abc',
  can_edit: true,
  created_at: '2026-06-08T00:00:00Z',
  ...overrides,
});

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/past-projects']}>
      <PastProjectsPage />
    </MemoryRouter>,
  );

describe('PastProjectsPage', () => {
  beforeEach(() => {
    sharedState.share = null;
    mockNavigate.mockReset();
    vi.mocked(createPastProjectShare).mockReset();
    vi.mocked(fetchPastProjectShare).mockReset();
    vi.mocked(updatePastProjectShare).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('redirects to the shareable link route after creating a share', async () => {
    vi.mocked(createPastProjectShare).mockResolvedValue(
      shareFixture({
        version: 1,
        note: 'Review note',
      }),
    );

    renderPage();
    fireEvent.click(
      screen.getByRole('button', {name: 'Create mocked share'}),
    );

    await waitFor(() => {
      expect(createPastProjectShare).toHaveBeenCalledWith(
        [sampleRow],
        'Spring finalists',
        'Review note',
      );
      expect(mockNavigate).toHaveBeenCalledWith(
        '/past-projects/share-abc',
      );
    });
  });

  it('serializes PATCHes and advances the optimistic version for queued edits', async () => {
    const initial = shareFixture();
    sharedState.share = initial;
    let resolveFirst!: (share: PastProjectShare) => void;
    vi.mocked(updatePastProjectShare)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValueOnce(
        shareFixture({
          rows: [sampleRow, addedRow],
          note: 'Updated note',
          version: 6,
        }),
      );

    renderPage();
    fireEvent.click(
      screen.getByRole('button', {name: 'Update mocked note'}),
    );
    fireEvent.click(
      screen.getByRole('button', {name: 'Add mocked row'}),
    );

    await waitFor(() =>
      expect(updatePastProjectShare).toHaveBeenCalledTimes(1),
    );
    expect(updatePastProjectShare).toHaveBeenNthCalledWith(
      1,
      initial.id,
      {note: 'Updated note', version: 4},
    );

    await act(async () => {
      resolveFirst(
        shareFixture({note: 'Updated note', version: 5}),
      );
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(updatePastProjectShare).toHaveBeenCalledTimes(2),
    );
    expect(updatePastProjectShare).toHaveBeenNthCalledWith(
      2,
      initial.id,
      {
        rows: [sampleRow, addedRow],
        version: 5,
      },
    );
  });

  it('rebases a queued stale row edit without erasing an in-flight row addition', async () => {
    const initial = shareFixture();
    sharedState.share = initial;
    let resolveAddition!: (share: PastProjectShare) => void;
    vi.mocked(updatePastProjectShare)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveAddition = resolve;
        }),
      )
      .mockResolvedValueOnce(
        shareFixture({
          rows: [
            {...sampleRow, team_name: 'Edited Team Alpha'},
            addedRow,
          ],
          version: 6,
        }),
      );

    renderPage();
    fireEvent.click(
      screen.getByRole('button', {name: 'Add mocked row'}),
    );
    fireEvent.click(
      screen.getByRole('button', {name: 'Edit mocked row'}),
    );

    await waitFor(() =>
      expect(updatePastProjectShare).toHaveBeenCalledTimes(1),
    );
    expect(updatePastProjectShare).toHaveBeenNthCalledWith(
      1,
      initial.id,
      {
        rows: [sampleRow, addedRow],
        version: 4,
      },
    );

    await act(async () => {
      resolveAddition(
        shareFixture({
          rows: [sampleRow, addedRow],
          version: 5,
        }),
      );
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(updatePastProjectShare).toHaveBeenCalledTimes(2),
    );
    expect(updatePastProjectShare).toHaveBeenNthCalledWith(
      2,
      initial.id,
      {
        rows: [
          {...sampleRow, team_name: 'Edited Team Alpha'},
          addedRow,
        ],
        version: 5,
      },
    );
  });

  it('stops stale queued writes, refetches, and shows the conflict', async () => {
    const initial = shareFixture({version: 2});
    const authoritative = shareFixture({
      note: 'Remote note',
      version: 3,
    });
    sharedState.share = initial;
    vi.mocked(updatePastProjectShare).mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          code: 'stale_snapshot',
          current: authoritative,
        },
      },
    });
    vi.mocked(fetchPastProjectShare).mockResolvedValue(authoritative);

    renderPage();
    fireEvent.click(
      screen.getByRole('button', {name: 'Update mocked note'}),
    );
    fireEvent.click(
      screen.getByRole('button', {name: 'Add mocked row'}),
    );

    const conflictAlert = await screen.findByRole('alert');
    await waitFor(() =>
      expect(conflictAlert).toHaveTextContent(
        /changed elsewhere.*latest version was reloaded/i,
      ),
    );
    await waitFor(() =>
      expect(fetchPastProjectShare).toHaveBeenCalledWith(initial.id),
    );
    expect(updatePastProjectShare).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.getByTestId('share-note')).toHaveTextContent(
        'Remote note',
      ),
    );
  });
});
