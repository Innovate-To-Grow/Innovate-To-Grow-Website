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

// Re-imported fresh in beforeEach: the visitor-token module keeps an in-memory
// copy, which must not leak from one test into the next.
let fetchAssistantConfig: typeof AssistantApi.fetchAssistantConfig;
let isBudgetError: typeof AssistantApi.isBudgetError;
let sendAssistantMessage: typeof AssistantApi.sendAssistantMessage;

/** Simulate a page reload: fresh module state, same localStorage. */
async function loadApi() {
  vi.resetModules();
  ({fetchAssistantConfig, isBudgetError, sendAssistantMessage} = await import('@/features/assistant/api/index'));
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

const CONFIG = {
  enabled: true,
  welcome_message: 'hi',
  starter_questions: ['q1'],
  unavailable_message: 'down',
  max_message_chars: 100,
};

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

  describe('fetchAssistantConfig', () => {
    it('fetches from /assistant/config/ and returns the body', async () => {
      const config = {
        enabled: true,
        welcome_message: 'hi',
        starter_questions: ['q1'],
        unavailable_message: 'down',
        max_message_chars: 100,
      };
      mocks.get.mockResolvedValue({data: config});

      const result = await fetchAssistantConfig();
      expect(mocks.get).toHaveBeenCalledWith('/assistant/config/');
      expect(result).toEqual(config);
    });

    it('propagates errors so the caller can fall back', async () => {
      mocks.get.mockRejectedValue(new Error('network'));
      await expect(fetchAssistantConfig()).rejects.toThrow('network');
    });
  });

  describe('sendAssistantMessage', () => {
    it('posts message + history + session_id and returns an ok result on success', async () => {
      mocks.post.mockResolvedValue({
        data: {available: true, reply: 'pong', usage: {inputTokens: 1, outputTokens: 2, totalTokens: 3}},
      });

      const result = await sendAssistantMessage('ping', [{role: 'user', content: 'earlier'}], 'sess-1');
      expect(mocks.post).toHaveBeenCalledWith('/assistant/chat/', {
        message: 'ping',
        history: [{role: 'user', content: 'earlier'}],
        session_id: 'sess-1',
      });
      expect(result).toEqual({status: 'ok', reply: 'pong', usage: {inputTokens: 1, outputTokens: 2, totalTokens: 3}});
    });

    it('returns an unavailable result when available is false', async () => {
      mocks.post.mockResolvedValue({data: {available: false, message: 'off'}});
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result).toEqual({status: 'unavailable', message: 'off'});
    });

    it('returns a budget result on HTTP 429', async () => {
      mocks.post.mockRejectedValue(
        axiosErrorWithStatus(429, {detail: 'This detail must not replace the standard budget message.'}),
      );
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result).toEqual({
        status: 'budget',
        message: 'The assistant has reached its usage limit for now. Please try again later.',
      });
    });

    it('does not blame the visitor for a limit that may be shared by everyone', async () => {
      mocks.post.mockRejectedValue(axiosErrorWithStatus(429, {code: 'budget_exceeded'}));
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result.status).toBe('budget');
      if (result.status === 'budget') {
        expect(result.message).not.toMatch(/\byou\b|\byou've\b|\byour\b/i);
      }
    });

    it('preserves a public-safe backend detail for retryable failures', async () => {
      mocks.post.mockRejectedValue(
        axiosErrorWithStatus(503, {
          detail: 'The assistant is temporarily unavailable. Please try again in a moment.',
          code: 'budget_unavailable',
        }),
      );
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result).toEqual({
        status: 'error',
        message: 'The assistant is temporarily unavailable. Please try again in a moment.',
      });
    });

    it('returns a generic error result when the backend body has no safe message', async () => {
      mocks.post.mockRejectedValue(axiosErrorWithStatus(502));
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result).toEqual({status: 'error', message: 'Something went wrong. Please try again.'});
    });

    it('returns a generic error result on a non-axios failure', async () => {
      mocks.post.mockRejectedValue(new Error('boom'));
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result.status).toBe('error');
    });
  });

  describe('visitor token', () => {
    it('adopts the token from the config response and persists it', async () => {
      mocks.get.mockResolvedValue({data: {...CONFIG, visitor_token: 'tok-1'}});

      const result = await fetchAssistantConfig();

      expect(result).toEqual({...CONFIG, visitor_token: 'tok-1'});
      expect(localStorage.getItem(VISITOR_KEY)).toBe('tok-1');
    });

    it('sends the held token in the request body, not in a header', async () => {
      mocks.get.mockResolvedValue({data: {...CONFIG, visitor_token: 'tok-1'}});
      mocks.post.mockResolvedValue({data: OK_BODY});
      await fetchAssistantConfig();

      await sendAssistantMessage('ping', [], 'sess-1');
      await sendAssistantMessage('again', [], 'sess-1');

      expect(mocks.post).toHaveBeenNthCalledWith(1, '/assistant/chat/', {
        message: 'ping',
        history: [],
        session_id: 'sess-1',
        visitor_token: 'tok-1',
      });
      expect(lastChatBody().visitor_token).toBe('tok-1');
      // url + body only: no per-request config, so no custom header (and no
      // CORS allow-list change) is involved.
      expect(mocks.post.mock.calls.every((call) => call.length === 2)).toBe(true);
    });

    it('takes the token once: later config responses do not change the identity', async () => {
      mocks.post.mockResolvedValue({data: OK_BODY});
      mocks.get.mockResolvedValueOnce({data: {...CONFIG, visitor_token: 'tok-1'}});
      await fetchAssistantConfig();

      // A reload fetches config again, and the backend mints a new token each time.
      await loadApi();
      mocks.get.mockResolvedValueOnce({data: {...CONFIG, visitor_token: 'tok-2'}});
      await fetchAssistantConfig();
      await sendAssistantMessage('ping', [], 'sess-1');

      expect(localStorage.getItem(VISITOR_KEY)).toBe('tok-1');
      expect(lastChatBody().visitor_token).toBe('tok-1');
    });

    it('refreshes from config when the held token is missing', async () => {
      mocks.post.mockResolvedValue({data: OK_BODY});
      mocks.get.mockResolvedValueOnce({data: {...CONFIG, visitor_token: 'tok-1'}});
      await fetchAssistantConfig();

      // Site data cleared, then a reload: the next config response is adopted.
      localStorage.clear();
      await loadApi();
      mocks.get.mockResolvedValueOnce({data: {...CONFIG, visitor_token: 'tok-2'}});
      await fetchAssistantConfig();
      await sendAssistantMessage('ping', [], 'sess-1');

      expect(localStorage.getItem(VISITOR_KEY)).toBe('tok-2');
      expect(lastChatBody().visitor_token).toBe('tok-2');
    });

    it('replaces a rejected token with the one a successful reply hands back', async () => {
      localStorage.setItem(VISITOR_KEY, 'expired-tok');
      mocks.post.mockResolvedValueOnce({data: {...OK_BODY, visitor_token: 'fresh-tok'}});
      mocks.post.mockResolvedValueOnce({data: OK_BODY});

      const first = await sendAssistantMessage('ping', [], 'sess-1');
      await sendAssistantMessage('again', [], 'sess-1');

      expect(first.status).toBe('ok');
      expect(mocks.post.mock.calls[0][1].visitor_token).toBe('expired-tok');
      expect(mocks.post.mock.calls[1][1].visitor_token).toBe('fresh-tok');
      expect(localStorage.getItem(VISITOR_KEY)).toBe('fresh-tok');
    });

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

    it('stores a token handed back with an "unavailable" answer', async () => {
      mocks.post.mockResolvedValue({data: {available: false, message: 'off', visitor_token: 'fresh-tok'}});

      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result).toEqual({status: 'unavailable', message: 'off'});
      expect(localStorage.getItem(VISITOR_KEY)).toBe('fresh-tok');
    });

    it('keeps the held token when a response carries none or a malformed one', async () => {
      localStorage.setItem(VISITOR_KEY, 'tok-1');
      mocks.post.mockResolvedValueOnce({data: OK_BODY});
      mocks.post.mockResolvedValueOnce({data: {...OK_BODY, visitor_token: 12345}});
      mocks.post.mockRejectedValueOnce(axiosErrorWithStatus(429, 'not an object'));
      mocks.post.mockRejectedValueOnce(new Error('network'));

      for (let attempt = 0; attempt < 4; attempt += 1) {
        await sendAssistantMessage('ping', [], 'sess-1');
      }

      expect(localStorage.getItem(VISITOR_KEY)).toBe('tok-1');
      expect(lastChatBody().visitor_token).toBe('tok-1');
    });

    it('works against a backend that does not issue tokens (older deploy)', async () => {
      mocks.get.mockResolvedValue({data: CONFIG});
      mocks.post.mockResolvedValue({data: OK_BODY});

      await fetchAssistantConfig();
      const result = await sendAssistantMessage('ping', [], 'sess-1');

      expect(result.status).toBe('ok');
      expect(localStorage.getItem(VISITOR_KEY)).toBeNull();
      expect(lastChatBody()).not.toHaveProperty('visitor_token');
    });

    it('tolerates localStorage failure: the token is kept in memory and still sent', async () => {
      vi.stubGlobal('localStorage', {
        getItem: () => {
          throw new Error('denied');
        },
        setItem: () => {
          throw new Error('denied');
        },
        removeItem: () => {
          throw new Error('denied');
        },
      });
      mocks.get.mockResolvedValue({data: {...CONFIG, visitor_token: 'tok-1'}});
      mocks.post.mockResolvedValueOnce({data: OK_BODY});
      mocks.post.mockResolvedValueOnce({data: {...OK_BODY, visitor_token: 'tok-2'}});
      mocks.post.mockResolvedValueOnce({data: OK_BODY});

      await expect(fetchAssistantConfig()).resolves.toEqual({...CONFIG, visitor_token: 'tok-1'});
      const first = await sendAssistantMessage('ping', [], 'sess-1');
      expect(first.status).toBe('ok');
      expect(lastChatBody().visitor_token).toBe('tok-1');

      // A replacement handed back by the backend is honoured in memory too.
      await sendAssistantMessage('again', [], 'sess-1');
      await sendAssistantMessage('once more', [], 'sess-1');
      expect(lastChatBody().visitor_token).toBe('tok-2');
    });
  });

  describe('isBudgetError', () => {
    it('is true only for axios 429 errors', () => {
      expect(isBudgetError(axiosErrorWithStatus(429))).toBe(true);
      expect(isBudgetError(axiosErrorWithStatus(500))).toBe(false);
      expect(isBudgetError(new Error('plain'))).toBe(false);
      expect(isBudgetError(null)).toBe(false);
    });
  });
});
