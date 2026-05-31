import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: apiMock,
}));

import {fetchCurrentSchedule} from './index';

describe('event API', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
  });

  it('fetches the active schedule by default', async () => {
    apiMock.get.mockResolvedValue({data: {event: {name: 'Active'}}});

    await fetchCurrentSchedule();

    expect(apiMock.get).toHaveBeenCalledWith('/event/schedule/', {});
  });

  it('passes schedule_id when fetching a selected schedule', async () => {
    apiMock.get.mockResolvedValue({data: {event: {name: 'Archived'}}});

    await fetchCurrentSchedule('schedule-123');

    expect(apiMock.get).toHaveBeenCalledWith('/event/schedule/', {
      params: {schedule_id: 'schedule-123'},
    });
  });
});
