import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));
const authApiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));
const mockGetStoredSession = vi.hoisted(() => vi.fn());
const mockIsDefinitiveAuthFailure = vi.hoisted(() =>
  vi.fn((error: unknown) =>
    Boolean(
      error &&
        typeof error === 'object' &&
        (error as {definitive?: boolean}).definitive,
    ),
  ),
);

vi.mock('@/lib/api', () => ({api: apiMock}));
vi.mock('@/features/auth', () => ({
  authApi: authApiMock,
  getStoredSession: mockGetStoredSession,
  isDefinitiveAuthFailure: mockIsDefinitiveAuthFailure,
}));

import {
  createRegistration,
  fetchCurrentSchedule,
  fetchMyTickets,
  fetchRegistrationEvents,
  fetchRegistrationOptions,
  resendTicketEmail,
  sendPhoneCode,
  verifyPhoneCode,
} from '../index';

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
    apiMock.post.mockReset();
    authApiMock.get.mockReset();
    authApiMock.post.mockReset();
    mockGetStoredSession.mockReset();
    mockGetStoredSession.mockReturnValue(null);
  });

  it('fetches public schedules with the public client', async () => {
    apiMock.get.mockResolvedValue({data: {event: {name: 'Active'}}});
    await fetchCurrentSchedule();
    expect(apiMock.get).toHaveBeenCalledWith('/event/schedule/', {});

    await fetchCurrentSchedule('schedule-123');
    expect(apiMock.get).toHaveBeenLastCalledWith('/event/schedule/', {
      params: {schedule_id: 'schedule-123'},
    });
  });

  describe('registration discovery', () => {
    it('uses the refresh-aware client when a session exists', async () => {
      mockGetStoredSession.mockReturnValue({generation: 'session-a'});
      authApiMock.get.mockResolvedValue({
        data: [{...eventFields, registration: null}],
      });

      const events = await fetchRegistrationEvents();

      expect(authApiMock.get).toHaveBeenCalledWith(
        '/event/registration-events/',
      );
      expect(apiMock.get).not.toHaveBeenCalled();
      expect(events).toEqual([{...eventFields, registration: null}]);
    });

    it('falls back to public discovery only after authenticated 401 handling fails', async () => {
      mockGetStoredSession.mockReturnValue({generation: 'session-a'});
      authApiMock.get.mockRejectedValue({
        response: {status: 401},
        definitive: true,
      });
      apiMock.get.mockResolvedValue({
        data: [{...eventFields, registration: null}],
      });

      await expect(fetchRegistrationEvents()).resolves.toEqual([
        {...eventFields, registration: null},
      ]);
      expect(apiMock.get).toHaveBeenCalledWith(
        '/event/registration-events/',
      );
    });

    it('does not replace member discovery data after a transient auth failure', async () => {
      mockGetStoredSession.mockReturnValue({generation: 'session-a'});
      const error = {response: {status: 401}};
      authApiMock.get.mockRejectedValue(error);

      await expect(fetchRegistrationEvents()).rejects.toBe(error);
      expect(apiMock.get).not.toHaveBeenCalled();
    });

    it('falls back to the legacy options endpoint when discovery 404s', async () => {
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

      await expect(fetchRegistrationEvents()).resolves.toEqual([
        {
          ...eventFields,
          end_date: '2026-10-22',
          registration: null,
        },
      ]);
      expect(apiMock.get).toHaveBeenNthCalledWith(
        2,
        '/event/registration-options/',
        {},
      );
    });

    it('returns an empty list when the legacy fallback also 404s', async () => {
      apiMock.get
        .mockRejectedValueOnce({response: {status: 404}})
        .mockRejectedValueOnce({response: {status: 404}});
      await expect(fetchRegistrationEvents()).resolves.toEqual([]);
    });

    it('passes event_slug and retains it for an anonymous 401 fallback', async () => {
      mockGetStoredSession.mockReturnValue({generation: 'session-a'});
      authApiMock.get.mockRejectedValue({
        response: {status: 401},
        definitive: true,
      });
      apiMock.get.mockResolvedValue({
        data: {...eventFields, registration: null},
      });

      await fetchRegistrationOptions('fall-showcase');

      expect(authApiMock.get).toHaveBeenCalledWith(
        '/event/registration-options/',
        {params: {event_slug: 'fall-showcase'}},
      );
      expect(apiMock.get).toHaveBeenCalledWith(
        '/event/registration-options/',
        {params: {event_slug: 'fall-showcase'}},
      );
    });
  });

  it('uses the refresh-aware client for every protected event operation', async () => {
    authApiMock.post
      .mockResolvedValueOnce({data: {id: 'registration-1'}})
      .mockResolvedValueOnce({data: {message: 'sent'}})
      .mockResolvedValueOnce({
        data: {
          detail: 'sent',
          phone: '+12025550123',
          challenge_id: 'challenge-1',
        },
      })
      .mockResolvedValueOnce({
        data: {
          detail: 'verified',
          verified: true,
          phone: '+12025550123',
          challenge_id: 'challenge-1',
        },
      });
    authApiMock.get.mockResolvedValue({data: [{id: 'registration-1'}]});

    await createRegistration({
      event_slug: 'fall-showcase',
      ticket_id: 'ticket-1',
      attendee_first_name: 'Ada',
      attendee_last_name: 'Lovelace',
      answers: [],
    });
    await fetchMyTickets();
    await resendTicketEmail('registration-1');
    await sendPhoneCode('2025550123', '1-US', 'fall-showcase');
    await verifyPhoneCode('2025550123', '123456', 'challenge-1', 'fall-showcase');

    expect(authApiMock.post).toHaveBeenNthCalledWith(
      1,
      '/event/registrations/',
      expect.objectContaining({event_slug: 'fall-showcase'}),
    );
    expect(authApiMock.get).toHaveBeenCalledWith('/event/my-tickets/');
    expect(authApiMock.post).toHaveBeenNthCalledWith(
      2,
      '/event/my-tickets/registration-1/resend-email/',
      {},
    );
    expect(authApiMock.post).toHaveBeenNthCalledWith(
      3,
      '/event/send-phone-code/',
      {
        phone: '2025550123',
        region: '1-US',
        event_slug: 'fall-showcase',
      },
    );
    expect(authApiMock.post).toHaveBeenNthCalledWith(
      4,
      '/event/verify-phone-code/',
      {
        phone: '2025550123',
        code: '123456',
        challenge_id: 'challenge-1',
        event_slug: 'fall-showcase',
      },
    );
    expect(apiMock.post).not.toHaveBeenCalled();
  });
});
