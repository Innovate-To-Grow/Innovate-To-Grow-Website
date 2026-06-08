import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';

import {PastProjectsPage} from './PastProjectsPage';
import {createPastProjectShare} from '@/features/projects/api';

const {mockNavigate, sampleRow} = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  sampleRow: {
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
  },
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('@/features/projects/api', () => ({
  createPastProjectShare: vi.fn(),
  updatePastProjectShare: vi.fn(),
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
  usePastProjectGridData: () => ({
    error: null,
    loading: false,
    rows: [sampleRow],
  }),
  usePastProjectShareData: () => ({
    error: null,
    loading: false,
    share: null,
  }),
}));

vi.mock('@/features/projects', () => ({
  createProjectGridItems: (rows: typeof sampleRow[]) => rows.map((row, index) => ({...row, __key: `row-${index}`})),
  MergedResultsTable: () => <div>Shared page table</div>,
  SharedPastProjectMergeSearch: () => <div>Shared merge search</div>,
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
    mockNavigate.mockReset();
    vi.mocked(createPastProjectShare).mockReset();
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
});
