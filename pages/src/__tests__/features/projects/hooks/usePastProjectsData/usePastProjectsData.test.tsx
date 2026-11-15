import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

const {mockFetchAllPastProjectArchive} = vi.hoisted(() => ({
  mockFetchAllPastProjectArchive: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    fetchAllPastProjectArchive: mockFetchAllPastProjectArchive,
  };
});

import {usePastProjectsData} from '@/features/projects/hooks/usePastProjectsData';
import type {CompactPastProjectRow} from '@/features/projects/api';

const makeProject = (overrides: Partial<CompactPastProjectRow> = {}): CompactPastProjectRow => ({
  id: 'p-1',
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Team A',
  project_title: 'Project A',
  organization: 'Org A',
  industry: 'Energy',
  track: 1,
  presentation_order: 2,
  ...overrides,
});

describe('usePastProjectsData', () => {
  afterEach(() => {
    cleanup();
    mockFetchAllPastProjectArchive.mockReset();
  });

  it('starts loading and maps a single page of rows', async () => {
    mockFetchAllPastProjectArchive.mockResolvedValue([
      makeProject(),
      makeProject({id: 'p-2', track: null, presentation_order: null, student_names: 'Ada Lovelace'}),
    ]);

    const {result} = renderHook(() => usePastProjectsData());

    expect(result.current.loading).toBe(true);
    expect(result.current.rows).toEqual([]);

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBeNull();
    expect(result.current.rows).toEqual([
      {
        Track: '1',
        Order: '2',
        'Year-Semester': '2025 Spring',
        Class: 'CAP',
        'Team#': '101',
        TeamName: 'Team A',
        'Project Title': 'Project A',
        Organization: 'Org A',
        Industry: 'Energy',
        Abstract: '',
        'Student Names': '',
        'Showcase Participation': '',
        NameTitle: '',
      },
      {
        Track: '',
        Order: '',
        'Year-Semester': '2025 Spring',
        Class: 'CAP',
        'Team#': '101',
        TeamName: 'Team A',
        'Project Title': 'Project A',
        Organization: 'Org A',
        Industry: 'Energy',
        Abstract: '',
        'Student Names': 'Ada Lovelace',
        'Showcase Participation': '',
        NameTitle: '',
      },
    ]);
  });

  it('loads every archive page through the shared loader', async () => {
    mockFetchAllPastProjectArchive.mockResolvedValue([makeProject(), makeProject({id: 'p-2'}), makeProject({id: 'p-3'})]);

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(mockFetchAllPastProjectArchive).toHaveBeenCalledTimes(1);
    expect(result.current.rows).toHaveLength(3);
  });

  it('passes the year and season into the archive query', async () => {
    mockFetchAllPastProjectArchive.mockResolvedValue([]);

    renderHook(() => usePastProjectsData({year: 2025, season: 1}));

    await waitFor(() => expect(mockFetchAllPastProjectArchive).toHaveBeenCalled());
    expect(mockFetchAllPastProjectArchive).toHaveBeenCalledWith({year: 2025, season: 1}, expect.any(AbortSignal));
  });

  it('surfaces an Error message', async () => {
    mockFetchAllPastProjectArchive.mockRejectedValue(new Error('offline'));

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('offline');
    expect(result.current.rows).toEqual([]);
  });

  it('falls back to a generic message for non-Error rejections', async () => {
    mockFetchAllPastProjectArchive.mockRejectedValue('network down');

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Failed to load past projects');
  });

  it('aborts the in-flight request on unmount', async () => {
    mockFetchAllPastProjectArchive.mockReturnValue(new Promise(() => {}));

    const {unmount} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(mockFetchAllPastProjectArchive).toHaveBeenCalled());

    unmount();

    const signal = mockFetchAllPastProjectArchive.mock.calls[0][1] as AbortSignal;
    expect(signal.aborted).toBe(true);
  });

  it('ignores a late resolution after the request has been aborted', async () => {
    let resolve!: (payload: CompactPastProjectRow[]) => void;
    mockFetchAllPastProjectArchive.mockReturnValue(
      new Promise<CompactPastProjectRow[]>((res) => {
        resolve = res;
      }),
    );

    const {unmount} = renderHook(() => usePastProjectsData());
    await waitFor(() => expect(mockFetchAllPastProjectArchive).toHaveBeenCalled());
    unmount();

    await act(async () => {
      resolve([makeProject()]);
    });
  });

  it('ignores a rejection after the request has been aborted', async () => {
    let reject!: (error: unknown) => void;
    mockFetchAllPastProjectArchive.mockReturnValue(
      new Promise<CompactPastProjectRow[]>((_, rej) => {
        reject = rej;
      }),
    );

    const {unmount} = renderHook(() => usePastProjectsData());
    await waitFor(() => expect(mockFetchAllPastProjectArchive).toHaveBeenCalled());
    unmount();

    await act(async () => {
      reject(new Error('late failure'));
    });
  });
});
