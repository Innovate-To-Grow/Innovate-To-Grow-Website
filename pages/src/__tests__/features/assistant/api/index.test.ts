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

  describe('isBudgetError', () => {
    it('is true only for axios 429 errors', () => {
      expect(isBudgetError(axiosErrorWithStatus(429))).toBe(true);
      expect(isBudgetError(axiosErrorWithStatus(500))).toBe(false);
      expect(isBudgetError(new Error('plain'))).toBe(false);
      expect(isBudgetError(null)).toBe(false);
    });
  });
});
