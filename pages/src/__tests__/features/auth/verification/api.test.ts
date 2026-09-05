import {beforeEach, expect, it, vi} from 'vitest';

const client = vi.hoisted(() => ({post: vi.fn(), get: vi.fn()}));
vi.mock('@/features/auth/api/client', () => ({authApi: client}));
import {createSendChallenge, fetchSendRequestStatus} from '@/features/auth/verification/api';

beforeEach(() => vi.clearAllMocks());

it('issues cancellable challenges with the browser session and a bounded timeout', async () => {
  const signal = new AbortController().signal;
  const challenge = {challenge_id: 'challenge', challenge: {}};
  client.post.mockResolvedValue({data: challenge});
  const input = {operation: 'login.request_code' as const, email: 'member@example.com'};
  await expect(createSendChallenge(input, signal)).resolves.toBe(challenge);
  expect(client.post).toHaveBeenCalledWith('/authn/send-verification/challenge/', input, {signal, timeout: 15_000, withCredentials: true});
});

it('checks only the requested send and retains browser credentials', async () => {
  const status = {request_id: 'request', status: 'unknown'};
  client.get.mockResolvedValue({data: status});
  await expect(fetchSendRequestStatus('request')).resolves.toBe(status);
  expect(client.get).toHaveBeenCalledWith('/authn/send-verification/requests/request/', {timeout: 10_000, withCredentials: true});
});
