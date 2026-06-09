import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';

import {PastProjectsPage} from '@/routes/PastProjectsPage/PastProjectsPage';
import {createPastProjectShare, updatePastProjectShare} from '@/features/projects/api';

const {gridState, mockNavigate, routeState, sampleRow, shareState} = vi.hoisted(() => {
  const sampleRow = {
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
  type Share = {
    id: string;
    name: string;
    rows: Array<typeof sampleRow>;
    note: string | null;
    details_text: string | null;
    share_url: string;
    can_edit: boolean;
    created_at: string;
  };

  return {
    gridState: {
      error: null as string | null,
      loading: false,
      rows: [sampleRow],
    },
    mockNavigate: vi.fn(),
    routeState: {
      shareId: undefined as string | undefined,
    },
    sampleRow,
    shareState: {
      error: null as string | null,
      loading: false,
      share: null as Share | null,
    },
  };
});

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({shareId: routeState.shareId}),
  };
});

vi.mock('@/features/projects/api', () => ({
  createPastProjectShare: vi.fn(),
  updatePastProjectShare: vi.fn(),
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
  usePastProjectGridData: () => ({
    error: gridState.error,
    loading: gridState.loading,
    rows: gridState.rows,
  }),
  usePastProjectShareData: () => ({
    error: shareState.error,
    loading: shareState.loading,
    share: shareState.share,
  }),
}));

vi.mock('@/features/projects', () => ({
  createProjectGridItems: (rows: typeof sampleRow[]) => rows.map((row, index) => ({...row, __key: `row-${index}`})),
  MergedResultsTable: ({
    onUpdateShare,
    title,
  }: {
    onUpdateShare?: (rows: typeof sampleRow[], note: string, name: string, detailsText: string) => Promise<void>;
    title?: string;
  }) => (
    <div>
      <h2>{title}</h2>
      <div>Shared page table</div>
      {onUpdateShare ? (
        <button
          type="button"
          onClick={() => void onUpdateShare([sampleRow], 'Updated note', 'Updated name', '<p>Updated</p>')}
        >
          Update shared page
        </button>
      ) : null}
    </div>
  ),
  SharedPastProjectMergeSearch: ({onAddRows}: {onAddRows: (rows: typeof sampleRow[]) => Promise<void>}) => (
    <button
      type="button"
      onClick={() => void onAddRows([{...sampleRow, team_number: '102', team_name: 'Team Beta'}])}
    >
      Add shared row
    </button>
  ),
  PastProjectsBuilder: ({
    onCreateShare,
  }: {
    onCreateShare: (rows: typeof sampleRow[], name: string, note: string, detailsText: string) => Promise<unknown>;
  }) => (
    <button
      type="button"
      onClick={() => void onCreateShare([sampleRow], 'Spring finalists', 'Review note', '<strong>Details</strong>')}
    >
      Create mocked share
    </button>
  ),
}));

describe('PastProjectsPage', () => {
  beforeEach(() => {
    routeState.shareId = undefined;
    gridState.error = null;
    gridState.loading = false;
    gridState.rows = [sampleRow];
    shareState.error = null;
    shareState.loading = false;
    shareState.share = null;
    mockNavigate.mockReset();
    vi.mocked(createPastProjectShare).mockReset();
    vi.mocked(updatePastProjectShare).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('redirects to the shareable link route after creating a share', async () => {
    vi.mocked(createPastProjectShare).mockResolvedValue({
      id: 'share-abc',
      name: 'Spring finalists',
      rows: [sampleRow],
      note: 'Review note',
      details_text: '<strong>Details</strong>',
      share_url: '/past-projects/share-abc',
      can_edit: true,
      created_at: '2026-06-08T00:00:00Z',
    });

    render(
      <MemoryRouter initialEntries={['/past-projects']}>
        <PastProjectsPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Create mocked share'}));

    await waitFor(() => {
      expect(createPastProjectShare).toHaveBeenCalledWith(
        [sampleRow],
        'Spring finalists',
        'Review note',
        '<strong>Details</strong>',
      );
      expect(mockNavigate).toHaveBeenCalledWith('/past-projects/share-abc');
    });
  });

  it('updates an editable shared page and can append rows from search', async () => {
    routeState.shareId = 'share-abc';
    shareState.share = {
      id: 'share-abc',
      name: 'Shared finalists',
      rows: [sampleRow],
      note: 'Original note',
      details_text: '<p>Original</p>',
      share_url: '/past-projects/share-abc',
      can_edit: true,
      created_at: '2026-06-08T00:00:00Z',
    };
    vi.mocked(updatePastProjectShare).mockImplementation(async (id, payload) => ({
      ...shareState.share!,
      id,
      rows: payload.rows,
      note: payload.note,
      name: payload.name,
      details_text: payload.details_text,
    }));

    render(
      <MemoryRouter initialEntries={['/past-projects/share-abc']}>
        <PastProjectsPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Update shared page'}));

    await waitFor(() => {
      expect(updatePastProjectShare).toHaveBeenCalledWith('share-abc', {
        rows: [sampleRow],
        note: 'Updated note',
        name: 'Updated name',
        details_text: '<p>Updated</p>',
      });
    });

    fireEvent.click(screen.getByRole('button', {name: 'Add shared row'}));

    await waitFor(() => {
      expect(updatePastProjectShare).toHaveBeenLastCalledWith('share-abc', {
        rows: [sampleRow, {...sampleRow, team_number: '102', team_name: 'Team Beta'}],
        note: 'Updated note',
        name: 'Updated name',
        details_text: '<p>Updated</p>',
      });
    });
  });

  it('shows shared-page loading and error states', () => {
    routeState.shareId = 'share-abc';
    shareState.loading = true;
    const {rerender} = render(
      <MemoryRouter initialEntries={['/past-projects/share-abc']}>
        <PastProjectsPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading shared results...')).toBeInTheDocument();

    shareState.loading = false;
    shareState.error = 'Shared page unavailable';
    rerender(
      <MemoryRouter initialEntries={['/past-projects/share-abc']}>
        <PastProjectsPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Shared page unavailable')).toBeInTheDocument();
  });
});
