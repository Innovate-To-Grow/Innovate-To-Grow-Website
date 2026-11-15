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
let sendAssistantMessage: typeof AssistantApi.sendAssistantMessage;

/** Simulate a page reload: fresh module state, same localStorage. */
async function loadApi() {
  vi.resetModules();
  ({fetchAssistantConfig, sendAssistantMessage} = await import('@/features/assistant/api/index'));
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

  describe('visitor token', () => {
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
});
