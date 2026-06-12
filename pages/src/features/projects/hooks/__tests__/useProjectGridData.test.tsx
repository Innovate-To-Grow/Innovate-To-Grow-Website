import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {usePastProjectGridData} from '../useProjectGridData';
import type {ProjectTableRow} from '@/features/projects/api';

const mockFetchAllPastProjects = vi.fn();

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    fetchAllPastProjects: (...args: unknown[]) => mockFetchAllPastProjects(...args),
  };
});

const makeProject = (overrides: Partial<ProjectTableRow>): ProjectTableRow => ({
  id: 'project-1',
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Solar Team',
  project_title: 'Solar Project',
  organization: 'Solar Org',
  industry: 'Energy',
  abstract: 'A solar project abstract.',
  student_names: 'Alex Student',
  track: null,
  presentation_order: null,
  ...overrides,
});

describe('usePastProjectGridData', () => {
  afterEach(() => {
    mockFetchAllPastProjects.mockReset();
  });

  it('keeps serving the previous rows, without flipping loading, while a refetch is in flight', async () => {
    let resolveSecond: (projects: ProjectTableRow[]) => void = () => {};
    mockFetchAllPastProjects
      .mockResolvedValueOnce([makeProject({project_title: 'First Load'})])
      .mockImplementationOnce(
        () =>
          new Promise<ProjectTableRow[]>((resolve) => {
            resolveSecond = resolve;
          }),
      );

    const {result} = renderHook(() => usePastProjectGridData());

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load']);

    act(() => result.current.refetch());

    // Stale-while-revalidate: the previous rows stay available and there is no loading flash,
    // so consumers keep their search tables (and per-table curation) mounted across a refresh.
    expect(result.current.loading).toBe(false);
    expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load']);

    await act(async () => {
      resolveSecond([
        makeProject({project_title: 'First Load'}),
        makeProject({id: 'project-2', project_title: 'Second Load'}),
      ]);
    });

    await waitFor(() =>
      expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load', 'Second Load']),
    );
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
