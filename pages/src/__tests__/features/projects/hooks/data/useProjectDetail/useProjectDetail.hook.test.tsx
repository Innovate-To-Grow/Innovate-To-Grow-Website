import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  useProjectDetail,
} from '@/features/projects/hooks/data/useProjectDetail';
import {
  ARCHIVE_PROJECT_ID,
  HVAC_PROJECT_ID,
  currentSchedulePayload,
} from '@/__tests__/features/projects/fixtures/currentSchedule';

const {mockFetchCurrentSchedule, mockFetchProjectDetail} = vi.hoisted(() => ({
  mockFetchCurrentSchedule: vi.fn(),
  mockFetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: (...args: unknown[]) => mockFetchCurrentSchedule(...args),
}));

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: (...args: unknown[]) => mockFetchProjectDetail(...args),
}));

const notFound = () => Object.assign(new Error('Request failed with status code 404'), {response: {status: 404}});
const serverError = () => Object.assign(new Error('Request failed with status code 502'), {response: {status: 502}});

describe('useProjectDetail', () => {
  beforeEach(() => {
    mockFetchCurrentSchedule.mockReset().mockResolvedValue(currentSchedulePayload());
    mockFetchProjectDetail.mockReset().mockRejectedValue(notFound());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads a current project', async () => {
    const {result} = renderHook(() => useProjectDetail(HVAC_PROJECT_ID, true));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.result?.project.project_title).toBe('ASHRAE HVAC Design Calculations');
  });

  it('says not found only when no source has the project', async () => {
    const {result} = renderHook(() => useProjectDetail(ARCHIVE_PROJECT_ID, true));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('not-found');
    expect(result.current.result).toBeNull();
  });

  it('says the load failed and loads again on retry', async () => {
    mockFetchCurrentSchedule.mockRejectedValueOnce(serverError());
    const {result} = renderHook(() => useProjectDetail(HVAC_PROJECT_ID, true));

    await waitFor(() => expect(result.current.error).toBe('failed'));

    act(() => result.current.retry());
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.result?.source).toBe('current');
    expect(mockFetchCurrentSchedule).toHaveBeenCalledTimes(2);
  });

  it('treats a missing id as not found without loading anything', () => {
    const {result} = renderHook(() => useProjectDetail(undefined, true));

    expect(result.current).toMatchObject({result: null, loading: false, error: 'not-found'});
    expect(mockFetchCurrentSchedule).not.toHaveBeenCalled();
  });

  it.each(['archive', 'past', 'current', 'past-shares', '../../event/projects', 'abc?x=1'])(
    'treats %s, which is not a project id, as not found without requesting it',
    (projectId) => {
      const {result} = renderHook(() => useProjectDetail(projectId, true));

      expect(result.current).toMatchObject({result: null, loading: false, error: 'not-found'});
      expect(mockFetchCurrentSchedule).not.toHaveBeenCalled();
      expect(mockFetchProjectDetail).not.toHaveBeenCalled();
    },
  );

  it('ignores a response that lands after unmount', async () => {
    let resolve!: (value: unknown) => void;
    mockFetchCurrentSchedule.mockReturnValue(new Promise((res) => (resolve = res)));
    const {unmount} = renderHook(() => useProjectDetail(HVAC_PROJECT_ID, true));
    unmount();

    await act(async () => {
      resolve(currentSchedulePayload());
    });
    expect(mockFetchProjectDetail).not.toHaveBeenCalled();
  });
});
