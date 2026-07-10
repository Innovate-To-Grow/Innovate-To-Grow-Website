import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

const mockGetAccessToken = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api-client', () => ({
  api: apiMock,
}));

vi.mock('@/features/auth', () => ({
  getAccessToken: mockGetAccessToken,
}));

import {fetchCurrentSchedule, fetchRegistrationEvents, fetchRegistrationOptions} from '../index';

const eventFields = {
  id: 'ev-1',
  name: 'Fall Showcase',
  slug: 'fall-showcase',
  date: '2026-10-20',
  location: 'Hall A',
  description: 'Annual showcase',
};

describe('event API', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
    mockGetAccessToken.mockReset();
    mockGetAccessToken.mockReturnValue(null);
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

  describe('fetchRegistrationEvents', () => {
    it('sends the auth header when a token is present', async () => {
      mockGetAccessToken.mockReturnValue('jwt-token');
      apiMock.get.mockResolvedValue({data: [{...eventFields, registration: null}]});

      const events = await fetchRegistrationEvents();

      expect(apiMock.get).toHaveBeenCalledWith('/event/registration-events/', {
        headers: {Authorization: 'Bearer jwt-token'},
      });
      expect(events).toEqual([{...eventFields, registration: null}]);
    });

    it('retries without auth on 401', async () => {
      mockGetAccessToken.mockReturnValue('expired-token');
      apiMock.get
        .mockRejectedValueOnce({response: {status: 401}})
        .mockResolvedValueOnce({data: [{...eventFields, registration: null}]});

      const events = await fetchRegistrationEvents();

      expect(apiMock.get).toHaveBeenNthCalledWith(2, '/event/registration-events/');
      expect(events).toEqual([{...eventFields, registration: null}]);
    });

    it('falls back to the legacy options endpoint when the route 404s', async () => {
      apiMock.get
        .mockRejectedValueOnce({response: {status: 404}})
        .mockResolvedValueOnce({
          data: {
            ...eventFields,
            end_date: '2026-10-22',
            registration: null,
            tickets: [],
            questions: [],
          },
        });

      const events = await fetchRegistrationEvents();

      expect(apiMock.get).toHaveBeenNthCalledWith(2, '/event/registration-options/', {});
      expect(events).toEqual([{
        ...eventFields,
        end_date: '2026-10-22',
        registration: null,
      }]);
    });

    it('returns an empty list when the legacy fallback also 404s', async () => {
      apiMock.get
        .mockRejectedValueOnce({response: {status: 404}})
        .mockRejectedValueOnce({response: {status: 404}});

      await expect(fetchRegistrationEvents()).resolves.toEqual([]);
    });

    it('rethrows non-404 errors from the legacy fallback', async () => {
      apiMock.get
        .mockRejectedValueOnce({response: {status: 404}})
        .mockRejectedValueOnce({response: {status: 500}});

      await expect(fetchRegistrationEvents()).rejects.toEqual({response: {status: 500}});
    });
  });

  describe('fetchRegistrationOptions', () => {
    it('passes event_slug when a slug is given', async () => {
      apiMock.get.mockResolvedValue({data: {...eventFields, registration: null}});

      await fetchRegistrationOptions('fall-showcase');

      expect(apiMock.get).toHaveBeenCalledWith('/event/registration-options/', {
        params: {event_slug: 'fall-showcase'},
      });
    });

    it('keeps event_slug on the 401 retry', async () => {
      mockGetAccessToken.mockReturnValue('expired-token');
      apiMock.get
        .mockRejectedValueOnce({response: {status: 401}})
        .mockResolvedValueOnce({data: {...eventFields, registration: null}});

      await fetchRegistrationOptions('fall-showcase');

      expect(apiMock.get).toHaveBeenNthCalledWith(2, '/event/registration-options/', {
        params: {event_slug: 'fall-showcase'},
      });
    });
  });
});
