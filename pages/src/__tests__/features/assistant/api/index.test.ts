import {AxiosError, AxiosHeaders} from 'axios';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: {get: mocks.get, post: mocks.post},
}));

import {fetchAssistantConfig, isBudgetError, sendAssistantMessage} from '@/features/assistant/api/index';

function axiosErrorWithStatus(status: number): AxiosError {
  const error = new AxiosError('boom');
  error.response = {
    status,
    statusText: '',
    data: {},
    headers: {},
    config: {headers: new AxiosHeaders()},
  };
  return error;
}

describe('assistant api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
      mocks.post.mockRejectedValue(axiosErrorWithStatus(429));
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result.status).toBe('budget');
    });

    it('returns a generic error result on other failures', async () => {
      mocks.post.mockRejectedValue(axiosErrorWithStatus(502));
      const result = await sendAssistantMessage('ping', [], 'sess-1');
      expect(result.status).toBe('error');
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
