import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

const authMock = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: apiMock,
}));

vi.mock('@/features/auth', () => ({
  getAccessToken: authMock.getAccessToken,
}));

import {
  createRegistration,
  fetchCurrentSchedule,
  fetchMyTickets,
  fetchRegistrationOptions,
  resendTicketEmail,
  sendPhoneCode,
  verifyPhoneCode,
} from '@/features/events/api/index';

describe('event API', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
    apiMock.post.mockReset();
    authMock.getAccessToken.mockReset();
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

  it('fetches registration options with auth headers and retries 401 publicly', async () => {
    authMock.getAccessToken.mockReturnValue('token');
    apiMock.get
      .mockRejectedValueOnce({response: {status: 401}})
      .mockResolvedValueOnce({data: {id: 'event', member_emails: []}});

    await expect(fetchRegistrationOptions()).resolves.toMatchObject({id: 'event'});

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/event/registration-options/', {
      headers: {Authorization: 'Bearer token'},
    });
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/event/registration-options/');
  });

  it('rethrows non-auth registration option failures', async () => {
    authMock.getAccessToken.mockReturnValue('token');
    apiMock.get.mockRejectedValue({response: {status: 503}});

    await expect(fetchRegistrationOptions()).rejects.toMatchObject({response: {status: 503}});
  });

  it('posts registration and phone verification payloads with auth headers', async () => {
    authMock.getAccessToken.mockReturnValue('token');
    apiMock.post.mockResolvedValue({data: {ok: true}});

    await createRegistration({
      event_slug: 'showcase',
      ticket_id: 'ticket',
      attendee_first_name: 'Ada',
      attendee_last_name: 'Lovelace',
      answers: [{question_id: 'q1', answer: 'Yes'}],
    });
    await resendTicketEmail('registration-id');
    await sendPhoneCode('2095551212', '1-US');
    await verifyPhoneCode('2095551212', '123456');

    const authHeaders = {headers: {Authorization: 'Bearer token'}};
    expect(apiMock.post).toHaveBeenNthCalledWith(
      1,
      '/event/registrations/',
      {
        event_slug: 'showcase',
        ticket_id: 'ticket',
        attendee_first_name: 'Ada',
        attendee_last_name: 'Lovelace',
        answers: [{question_id: 'q1', answer: 'Yes'}],
      },
      authHeaders,
    );
    expect(apiMock.post).toHaveBeenNthCalledWith(
      2,
      '/event/my-tickets/registration-id/resend-email/',
      {},
      authHeaders,
    );
    expect(apiMock.post).toHaveBeenNthCalledWith(
      3,
      '/event/send-phone-code/',
      {phone: '2095551212', region: '1-US'},
      authHeaders,
    );
    expect(apiMock.post).toHaveBeenNthCalledWith(
      4,
      '/event/verify-phone-code/',
      {phone: '2095551212', code: '123456'},
      authHeaders,
    );
  });

  it('fetches the current member tickets with auth headers', async () => {
    authMock.getAccessToken.mockReturnValue('token');
    apiMock.get.mockResolvedValue({data: [{id: 'ticket'}]});

    await expect(fetchMyTickets()).resolves.toEqual([{id: 'ticket'}]);

    expect(apiMock.get).toHaveBeenCalledWith('/event/my-tickets/', {
      headers: {Authorization: 'Bearer token'},
    });
  });
});
