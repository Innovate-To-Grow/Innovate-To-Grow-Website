import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

const {mockFetchCurrentSchedule} = vi.hoisted(() => ({
  mockFetchCurrentSchedule: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/events/api')>();
  return {
    ...actual,
    fetchCurrentSchedule: mockFetchCurrentSchedule,
  };
});

import {useCurrentEventSchedule} from '@/features/events/hooks/useCurrentEventSchedule';
import type {EventSchedulePayload} from '@/features/events/api';

const makePayload = (overrides: Partial<EventSchedulePayload> = {}): EventSchedulePayload => ({
  event: {
    id: 'ev-1',
    name: 'Demo Day',
    slug: 'demo-day',
    date: '2026-05-07',
    location: 'Conference Center',
    description: 'Presentation schedule',
  },
  show_winners: false,
  grand_winners: [],
  expo: {title: 'Expo', location: '', items: []},
  presentations_title: 'PRESENTATIONS',
  sections: [],
  awards: {title: 'Awards', location: '', items: []},
  projects: [],
  ...overrides,
});

const axiosError = (detail: unknown) => ({
  isAxiosError: true,
  response: {data: {detail}},
});

describe('useCurrentEventSchedule', () => {
  afterEach(() => {
    cleanup();
    mockFetchCurrentSchedule.mockReset();
  });

  it('starts loading and resolves the schedule payload', async () => {
    mockFetchCurrentSchedule.mockResolvedValue(makePayload());

    const {result} = renderHook(() => useCurrentEventSchedule());

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual(makePayload());
    expect(result.current.error).toBeNull();
  });

  it('passes a schedule id through to the API', async () => {
    mockFetchCurrentSchedule.mockResolvedValue(makePayload());

    renderHook(() => useCurrentEventSchedule('schedule-123'));

    await waitFor(() => expect(mockFetchCurrentSchedule).toHaveBeenCalled());
    expect(mockFetchCurrentSchedule).toHaveBeenCalledWith('schedule-123');
  });

  it('refetches when the schedule id changes', async () => {
    mockFetchCurrentSchedule.mockResolvedValue(makePayload());

    const {result, rerender} = renderHook(({id}) => useCurrentEventSchedule(id), {
      initialProps: {id: null as string | null},
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockFetchCurrentSchedule).toHaveBeenCalledTimes(1);

    rerender({id: 'schedule-2'});
    await waitFor(() => expect(mockFetchCurrentSchedule).toHaveBeenCalledTimes(2));
    expect(mockFetchCurrentSchedule).toHaveBeenLastCalledWith('schedule-2');
  });

  it('surfaces a short detail string from an axios error', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(axiosError('Schedule not found'));

    const {result} = renderHook(() => useCurrentEventSchedule());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Schedule not found');
    expect(result.current.data).toBeNull();
  });

  it('falls back to the generic message when the detail is too long', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(axiosError('x'.repeat(301)));

    const {result} = renderHook(() => useCurrentEventSchedule());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(
      'Failed to load event schedule. Please try again later.',
    );
  });

  it('falls back to the generic message when the detail is not a string', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(axiosError({msg: 'nope'}));

    const {result} = renderHook(() => useCurrentEventSchedule());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(
      'Failed to load event schedule. Please try again later.',
    );
  });

  it('falls back to the generic message for non-axios errors', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => useCurrentEventSchedule());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(
      'Failed to load event schedule. Please try again later.',
    );
  });

  it('ignores a resolution that arrives after unmount', async () => {
    let resolve!: (payload: EventSchedulePayload) => void;
    mockFetchCurrentSchedule.mockReturnValue(
      new Promise<EventSchedulePayload>((res) => {
        resolve = res;
      }),
    );

    const {result, unmount} = renderHook(() => useCurrentEventSchedule());
    expect(result.current.loading).toBe(true);

    unmount();

    await act(async () => {
      resolve(makePayload());
    });
  });

  it('ignores a rejection that arrives after unmount', async () => {
    let reject!: (error: unknown) => void;
    mockFetchCurrentSchedule.mockReturnValue(
      new Promise<EventSchedulePayload>((_, rej) => {
        reject = rej;
      }),
    );

    const {result, unmount} = renderHook(() => useCurrentEventSchedule());
    expect(result.current.loading).toBe(true);

    unmount();

    await act(async () => {
      reject(axiosError('late failure'));
    });
  });
});
