import {renderHook, waitFor} from '@testing-library/react';
import axios from 'axios';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {useCurrentEventSchedule} from '@/features/events/hooks/useCurrentEventSchedule';
import type {EventSchedulePayload} from '@/features/events/api';

const scheduleMocks = vi.hoisted(() => ({
  fetchCurrentSchedule: vi.fn(),
}));

vi.mock('@/features/events/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/events/api')>('@/features/events/api');
  return {
    ...actual,
    fetchCurrentSchedule: scheduleMocks.fetchCurrentSchedule,
  };
});

const payload: EventSchedulePayload = {
  event: {id: 'event-1', name: 'Demo Day', slug: 'demo-day', date: '2026-05-01', location: 'Campus', description: ''},
  show_winners: false,
  grand_winners: [],
  expo: {title: 'Expo', location: '', items: []},
  presentations_title: 'Presentations',
  sections: [],
  awards: {title: 'Awards', location: '', items: []},
  projects: [],
};

describe('useCurrentEventSchedule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scheduleMocks.fetchCurrentSchedule.mockResolvedValue(payload);
  });

  it('loads the current schedule and refetches when the schedule id changes', async () => {
    const {result, rerender} = renderHook(({scheduleId}) => useCurrentEventSchedule(scheduleId), {
      initialProps: {scheduleId: 'schedule-1' as string | null},
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe(payload));
    expect(result.current.loading).toBe(false);
    expect(scheduleMocks.fetchCurrentSchedule).toHaveBeenCalledWith('schedule-1');

    rerender({scheduleId: 'schedule-2'});
    await waitFor(() => expect(scheduleMocks.fetchCurrentSchedule).toHaveBeenCalledWith('schedule-2'));
  });

  it('uses safe API detail errors and a fallback message for unknown failures', async () => {
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(true);
    scheduleMocks.fetchCurrentSchedule.mockRejectedValueOnce({
      response: {data: {detail: 'Schedule is not published yet.'}},
    });

    const detail = renderHook(() => useCurrentEventSchedule());
    await waitFor(() => expect(detail.result.current.error).toBe('Schedule is not published yet.'));

    vi.mocked(axios.isAxiosError).mockReturnValue(false);
    scheduleMocks.fetchCurrentSchedule.mockRejectedValueOnce(new Error('offline'));
    const fallback = renderHook(() => useCurrentEventSchedule());
    await waitFor(() => expect(fallback.result.current.error).toBe('Failed to load event schedule. Please try again later.'));
  });
});
