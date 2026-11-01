import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {CompactPastProjectRow} from '@/features/projects/api';
import {PROJECT_LIST_LOAD_ERROR, useAllProjectGridData} from '@/features/projects/hooks/useProjectGridData';

const {mockFetchAllProjectsCatalog, mockFetchAllPastProjectArchive} = vi.hoisted(() => ({
  mockFetchAllProjectsCatalog: vi.fn(),
  mockFetchAllPastProjectArchive: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchAllProjectsCatalog: (...args: unknown[]) => mockFetchAllProjectsCatalog(...args),
  fetchAllPastProjectArchive: (...args: unknown[]) => mockFetchAllPastProjectArchive(...args),
}));

const CURRENT_ID = '33333333-3333-4333-8333-333333333333';

const project = (overrides: Partial<CompactPastProjectRow>): CompactPastProjectRow => ({
  id: 'archive-1',
  semester_label: '2026-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Solar Project',
  organization: 'Solar Org',
  industry: 'Energy',
  student_names: 'Ada Lovelace',
  track: null,
  presentation_order: null,
  catalog: 'archive',
  is_presenting: null,
  current_project_id: null,
  ...overrides,
});

describe('useAllProjectGridData', () => {
  afterEach(() => {
    mockFetchAllProjectsCatalog.mockReset();
    mockFetchAllPastProjectArchive.mockReset();
  });

  it("loads every project, this semester's and the archive's, as grid rows", async () => {
    mockFetchAllProjectsCatalog.mockResolvedValue([
      project({id: CURRENT_ID, semester_label: '2026 Fall', catalog: 'current', is_presenting: true}),
      project({}),
    ]);

    const {result} = renderHook(() => useAllProjectGridData());

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockFetchAllProjectsCatalog).toHaveBeenCalledWith({}, expect.any(AbortSignal));
    expect(mockFetchAllPastProjectArchive).not.toHaveBeenCalled();
    expect(result.current.rows.map((row) => [row.id, row.semester_label, row.catalog, row.is_presenting])).toEqual([
      [CURRENT_ID, '2026 Fall', 'current', 'Yes'],
      ['archive-1', '2026 Spring', 'archive', ''],
    ]);
    expect(result.current.error).toBeNull();
  });

  it('keeps serving its rows while a refetch is in flight, and after one fails', async () => {
    mockFetchAllProjectsCatalog
      .mockResolvedValueOnce([project({project_title: 'First Load'})])
      .mockRejectedValueOnce(new Error('Request failed with status code 503'));

    const {result} = renderHook(() => useAllProjectGridData());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const firstRows = result.current.rows;

    act(() => result.current.refetch());
    expect(result.current.loading).toBe(false);
    expect(result.current.rows).toBe(firstRows);
    await waitFor(() => expect(result.current.error).toBe(PROJECT_LIST_LOAD_ERROR));
    expect(result.current.rows).toBe(firstRows);
  });

  it('reports a first load that failed in plain words', async () => {
    mockFetchAllProjectsCatalog.mockRejectedValue(new Error('Network Error'));

    const {result} = renderHook(() => useAllProjectGridData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current).toMatchObject({rows: [], error: PROJECT_LIST_LOAD_ERROR});
  });

  it('loads nothing while disabled', () => {
    const {result} = renderHook(() => useAllProjectGridData(false));

    expect(result.current).toEqual({rows: [], loading: false, error: null, refetch: expect.any(Function)});
    expect(mockFetchAllProjectsCatalog).not.toHaveBeenCalled();
  });
});
