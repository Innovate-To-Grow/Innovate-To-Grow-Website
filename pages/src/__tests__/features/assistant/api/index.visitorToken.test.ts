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
  });
});
