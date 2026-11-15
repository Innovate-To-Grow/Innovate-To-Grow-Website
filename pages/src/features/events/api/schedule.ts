import { api } from '@/lib/api';
import type {EventSchedulePayload} from './types';

export async function fetchCurrentSchedule(
  scheduleId?: string | null,
  {signal, timeout}: {signal?: AbortSignal; timeout?: number} = {},
): Promise<EventSchedulePayload> {
  const response = await api.get<EventSchedulePayload>('/event/schedule/', {
    ...(scheduleId ? {params: {schedule_id: scheduleId}} : {}),
    ...(signal ? {signal} : {}),
    ...(timeout ? {timeout} : {}),
  });
  return response.data;
}
