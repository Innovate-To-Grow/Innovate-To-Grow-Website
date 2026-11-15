import {AxiosError, AxiosHeaders} from 'axios';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type * as AssistantApi from '@/features/assistant/api/index';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: mocks.get, post: mocks.post},
}));

const VISITOR_KEY = 'itg-assistant-visitor';
let sendAssistantMessage: typeof AssistantApi.sendAssistantMessage;

/** Simulate a page reload: fresh module state, same localStorage. */
async function loadApi() {
  vi.resetModules();
  ({sendAssistantMessage} = await import('@/features/assistant/api/index'));
}

function axiosErrorWithStatus(status: number, data: unknown = {}): AxiosError {
  const error = new AxiosError('boom');
  error.response = {
    status,
    statusText: '',
    data,
    headers: {},
    config: {headers: new AxiosHeaders()},
  };
  return error;
}

const OK_BODY = {available: true, reply: 'pong', usage: {inputTokens: 1, outputTokens: 2, totalTokens: 3}};

/** The body of the most recent POST /assistant/chat/. */
function lastChatBody(): Record<string, unknown> {
  return mocks.post.mock.calls[mocks.post.mock.calls.length - 1][1] as Record<string, unknown>;
}

describe('assistant api', () => {
  beforeEach(async () => {
    // reset (not clear): queued once-responses and default implementations
    // must not leak from one test into the next.
    vi.resetAllMocks();
    localStorage.clear();
    await loadApi();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  describe('visitor token', () => {
    it('re-sends once with the token a 429 hands back, so a lapsed token costs no answer', async () => {
      localStorage.setItem(VISITOR_KEY, 'expired-tok');
      mocks.post.mockRejectedValueOnce(
        axiosErrorWithStatus(429, {detail: 'limit', code: 'budget_exceeded', visitor_token: 'fresh-tok'}),
      );
      mocks.post.mockResolvedValueOnce({data: OK_BODY});

      const result = await sendAssistantMessage('ping', [{role: 'user', content: 'earlier'}], 'sess-1');

      expect(result).toEqual({status: 'ok', reply: 'pong', usage: OK_BODY.usage});
      expect(mocks.post).toHaveBeenCalledTimes(2);
      expect(mocks.post.mock.calls[0][1].visitor_token).toBe('expired-tok');
      expect(mocks.post).toHaveBeenNthCalledWith(2, '/assistant/chat/', {
        message: 'ping',
        history: [{role: 'user', content: 'earlier'}],
        session_id: 'sess-1',
        visitor_token: 'fresh-tok',
      });
      expect(localStorage.getItem(VISITOR_KEY)).toBe('fresh-tok');
    });

    it('re-sends when a throttled request without any token is handed one', async () => {
      mocks.post.mockRejectedValueOnce(
        axiosErrorWithStatus(429, {detail: 'Request was throttled.', visitor_token: 'fresh-tok'}),
      );
      mocks.post.mockResolvedValueOnce({data: OK_BODY});

      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result.status).toBe('ok');
      expect(mocks.post.mock.calls[0][1]).not.toHaveProperty('visitor_token');
      expect(lastChatBody().visitor_token).toBe('fresh-tok');
    });

    it('re-sends at most once, even if every 429 hands back another token', async () => {
      localStorage.setItem(VISITOR_KEY, 'expired-tok');
      mocks.post.mockRejectedValueOnce(axiosErrorWithStatus(429, {detail: 'limit', visitor_token: 'tok-a'}));
      mocks.post.mockRejectedValueOnce(axiosErrorWithStatus(429, {detail: 'limit', visitor_token: 'tok-b'}));
      mocks.post.mockResolvedValue({data: OK_BODY});

      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result).toEqual({
        status: 'budget',
        message: 'The assistant has reached its usage limit for now. Please try again later.',
      });
      expect(mocks.post).toHaveBeenCalledTimes(2);
      expect(localStorage.getItem(VISITOR_KEY)).toBe('tok-b');
    });

    it('does not re-send a 429 that hands back no token (the limit is this visitor\'s own or global)', async () => {
      localStorage.setItem(VISITOR_KEY, 'tok-1');
      mocks.post.mockRejectedValueOnce(axiosErrorWithStatus(429, {detail: 'limit', code: 'budget_exceeded'}));
      mocks.post.mockResolvedValue({data: OK_BODY});

      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result.status).toBe('budget');
      expect(mocks.post).toHaveBeenCalledTimes(1);
    });

    it('does not re-send a 429 that hands back the token it was sent', async () => {
      localStorage.setItem(VISITOR_KEY, 'tok-1');
      mocks.post.mockRejectedValueOnce(axiosErrorWithStatus(429, {detail: 'limit', visitor_token: 'tok-1'}));
      mocks.post.mockResolvedValue({data: OK_BODY});

      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result.status).toBe('budget');
      expect(mocks.post).toHaveBeenCalledTimes(1);
    });

    it('stores but does not re-send when a non-429 failure hands back a token', async () => {
      localStorage.setItem(VISITOR_KEY, 'expired-tok');
      mocks.post.mockRejectedValueOnce(
        axiosErrorWithStatus(502, {detail: 'The assistant ran into a problem.', visitor_token: 'fresh-tok'}),
      );
      mocks.post.mockResolvedValue({data: OK_BODY});

      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result).toEqual({status: 'error', message: 'The assistant ran into a problem.'});
      expect(mocks.post).toHaveBeenCalledTimes(1);
      expect(localStorage.getItem(VISITOR_KEY)).toBe('fresh-tok');
    });
  });
});
