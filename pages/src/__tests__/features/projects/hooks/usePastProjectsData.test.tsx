import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

const {mockFetchPastProjectArchive} = vi.hoisted(() => ({
  mockFetchPastProjectArchive: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    fetchPastProjectArchive: mockFetchPastProjectArchive,
  };
});

import {usePastProjectsData} from '@/features/projects/hooks/usePastProjectsData';
import type {CompactPastProjectRow, PaginatedResponse} from '@/features/projects/api';

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

const makePage = (
  results: CompactPastProjectRow[],
  count = results.length,
): PaginatedResponse<CompactPastProjectRow> => ({
  count,
  next: null,
  previous: null,
  results,
});

describe('usePastProjectsData', () => {
  afterEach(() => {
    cleanup();
    mockFetchPastProjectArchive.mockReset();
  });

  it('starts loading and maps a single page of rows', async () => {
    mockFetchPastProjectArchive.mockResolvedValue(
      makePage([makeProject(), makeProject({id: 'p-2', track: null, presentation_order: null})]),
    );

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
        'Student Names': '',
        'Showcase Participation': '',
        NameTitle: '',
      },
    ]);
  });

  it('paginates until all rows are collected', async () => {
    mockFetchPastProjectArchive
      .mockResolvedValueOnce(makePage([makeProject(), makeProject({id: 'p-2'})], 3))
      .mockResolvedValueOnce(makePage([makeProject({id: 'p-3'})], 3));

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(mockFetchPastProjectArchive).toHaveBeenCalledTimes(2);
    expect(mockFetchPastProjectArchive).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({page: 1, page_size: 100}),
      expect.any(AbortSignal),
    );
    expect(mockFetchPastProjectArchive).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({page: 2, page_size: 100}),
      expect.any(AbortSignal),
    );
    expect(result.current.rows).toHaveLength(3);
  });

  it('passes the year and season into the archive query', async () => {
    mockFetchPastProjectArchive.mockResolvedValue(makePage([]));

    renderHook(() => usePastProjectsData({year: 2025, season: 1}));

    await waitFor(() => expect(mockFetchPastProjectArchive).toHaveBeenCalled());
    expect(mockFetchPastProjectArchive).toHaveBeenCalledWith(
      expect.objectContaining({page: 1, page_size: 100, year: 2025, season: 1}),
      expect.any(AbortSignal),
    );
  });

  it('surfaces an Error message', async () => {
    mockFetchPastProjectArchive.mockRejectedValue(new Error('offline'));

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('offline');
    expect(result.current.rows).toEqual([]);
  });

  it('falls back to a generic message for non-Error rejections', async () => {
    mockFetchPastProjectArchive.mockRejectedValue('network down');

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Failed to load past projects');
  });

  it('aborts the in-flight request on unmount', async () => {
    mockFetchPastProjectArchive.mockReturnValue(new Promise(() => {}));

    const {unmount} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(mockFetchPastProjectArchive).toHaveBeenCalled());

    unmount();

    const signal = mockFetchPastProjectArchive.mock.calls[0][1] as AbortSignal;
    expect(signal.aborted).toBe(true);
  });

  it('ignores a late resolution after the request has been aborted', async () => {
    let resolve!: (payload: PaginatedResponse<CompactPastProjectRow>) => void;
    mockFetchPastProjectArchive.mockReturnValue(
      new Promise<PaginatedResponse<CompactPastProjectRow>>((res) => {
        resolve = res;
      }),
    );

    const {unmount} = renderHook(() => usePastProjectsData());
    await waitFor(() => expect(mockFetchPastProjectArchive).toHaveBeenCalled());
    unmount();

    await act(async () => {
      resolve(makePage([makeProject()]));
    });
  });

  it('ignores a rejection after the request has been aborted', async () => {
    let reject!: (error: unknown) => void;
    mockFetchPastProjectArchive.mockReturnValue(
      new Promise<PaginatedResponse<CompactPastProjectRow>>((_, rej) => {
        reject = rej;
      }),
    );

    const {unmount} = renderHook(() => usePastProjectsData());
    await waitFor(() => expect(mockFetchPastProjectArchive).toHaveBeenCalled());
    unmount();

    await act(async () => {
      reject(new Error('late failure'));
    });
  });
});
