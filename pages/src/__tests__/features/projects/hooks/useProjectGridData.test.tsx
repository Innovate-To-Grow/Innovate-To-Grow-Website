import {act, renderHook, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const projectsApiMock = vi.hoisted(() => ({
  fetchAllPastProjects: vi.fn(),
  fetchPastProjectShare: vi.fn(),
  scheduleProjectToGridRow: vi.fn((row: {team_name: string}) => ({team_name: row.team_name, is_presenting: 'Yes'})),
  toProjectGridRow: vi.fn((row: {team_name: string}) => ({team_name: row.team_name, is_presenting: 'No'})),
}));

const eventsApiMock = vi.hoisted(() => ({
  fetchCurrentSchedule: vi.fn(),
}));

vi.mock('@/features/projects/api', () => projectsApiMock);
vi.mock('@/features/events/api', () => eventsApiMock);

import {
  useCurrentProjectGridData,
  usePastProjectGridData,
  usePastProjectShareData,
} from '@/features/projects/hooks/useProjectGridData';

describe('project grid data hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not fetch when current project loading is disabled', () => {
    const {result} = renderHook(() => useCurrentProjectGridData(false));

    expect(result.current).toMatchObject({rows: [], loading: false, error: null});
    expect(eventsApiMock.fetchCurrentSchedule).not.toHaveBeenCalled();
  });

  it('loads and refetches current project rows', async () => {
    eventsApiMock.fetchCurrentSchedule
      .mockResolvedValueOnce({projects: [{team_name: 'First'}]})
      .mockResolvedValueOnce({projects: [{team_name: 'Second'}]});

    const {result} = renderHook(() => useCurrentProjectGridData());

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows).toEqual([{team_name: 'First', is_presenting: 'Yes'}]);

    await act(async () => {
      result.current.refetch();
    });

    await waitFor(() => expect(result.current.rows).toEqual([{team_name: 'Second', is_presenting: 'Yes'}]));
    expect(eventsApiMock.fetchCurrentSchedule).toHaveBeenCalledTimes(2);
  });

  it('reports current project load failures', async () => {
    eventsApiMock.fetchCurrentSchedule.mockRejectedValue(new Error('schedule offline'));

    const {result} = renderHook(() => useCurrentProjectGridData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('schedule offline');
    expect(result.current.rows).toEqual([]);
  });

  it('loads past project rows and reports fallback errors', async () => {
    projectsApiMock.fetchAllPastProjects.mockResolvedValueOnce([{team_name: 'Archive'}]).mockRejectedValueOnce('bad');

    const success = renderHook(() => usePastProjectGridData());
    await waitFor(() => expect(success.result.current.loading).toBe(false));
    expect(success.result.current.rows).toEqual([{team_name: 'Archive', is_presenting: 'No'}]);

    const failure = renderHook(() => usePastProjectGridData());
    await waitFor(() => expect(failure.result.current.loading).toBe(false));
    expect(failure.result.current.error).toBe('Failed to load past projects');
  });

  it('handles disabled, loaded, and failed shared project data', async () => {
    const disabled = renderHook(() => usePastProjectShareData(undefined));
    expect(disabled.result.current).toMatchObject({share: null, loading: false, error: null});

    projectsApiMock.fetchPastProjectShare.mockResolvedValueOnce({id: 'share'}).mockRejectedValueOnce(new Error('missing'));

    const loaded = renderHook(() => usePastProjectShareData('share'));
    await waitFor(() => expect(loaded.result.current.loading).toBe(false));
    expect(loaded.result.current.share).toEqual({id: 'share'});

    const failed = renderHook(() => usePastProjectShareData('missing'));
    await waitFor(() => expect(failed.result.current.loading).toBe(false));
    expect(failed.result.current.error).toBe('missing');
  });
});
