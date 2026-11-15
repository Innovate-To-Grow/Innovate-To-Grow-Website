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
vi.mock('@/features/auth', async () => ({
  authApi: authApiMock,
  getStoredSession: mockGetStoredSession,
  isDefinitiveAuthFailure: mockIsDefinitiveAuthFailure,
  // The send-verification flow is replaced for every test by src/__tests__/core/setup.ts.
  withVerifiedSend: (await import('@/features/auth/verification')).withVerifiedSend,
}));

import {
  fetchRegistrationEvents,
  fetchRegistrationOptions,
} from '@/features/events/api/index';

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

  describe('registration discovery', () => {
    it('uses the refresh-aware client when a session exists', async () => {
      mockGetStoredSession.mockReturnValue({generation: 'session-a'});
      authApiMock.get.mockResolvedValue({
        data: [{...eventFields, registration: null}],
      });

      const events = await fetchRegistrationEvents();

      expect(authApiMock.get).toHaveBeenCalledWith(
        '/event/registration-events/',
        {requireFreshIdentity: true},
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

    it('preserves legacy required-phone behavior while honoring explicit new settings', async () => {
      apiMock.get.mockResolvedValueOnce({data: {...eventFields, collect_phone: true, verify_phone: true}});
      expect(await fetchRegistrationOptions()).toEqual(expect.objectContaining({
        require_phone: true, verify_secondary_email: false, require_secondary_email: false,
      }));
      apiMock.get.mockResolvedValueOnce({data: {
        ...eventFields, collect_phone: true, verify_phone: true, require_phone: false,
        verify_secondary_email: true, require_secondary_email: false,
      }});
      expect(await fetchRegistrationOptions()).toEqual(expect.objectContaining({
        require_phone: false, verify_secondary_email: true, require_secondary_email: false,
      }));
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
        {params: {event_slug: 'fall-showcase'}, requireFreshIdentity: true},
      );
      expect(apiMock.get).toHaveBeenCalledWith(
        '/event/registration-options/',
        {params: {event_slug: 'fall-showcase'}},
      );
    });
  });

});
