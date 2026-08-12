import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  persist: vi.fn(),
  clearProfileCompletion: vi.fn(),
}));

vi.mock('@/features/auth/api/client', () => ({
  authApi: {post: mocks.post},
}));

vi.mock('@/lib/security', () => ({
  encryptPasswordWithCurrentKey: vi.fn(),
  clearKeyCache: vi.fn(),
}));

vi.mock('@/features/auth/api/storage', () => ({
  persistAuthSession: mocks.persist,
  clearProfileCompletionRequired: mocks.clearProfileCompletion,
}));

vi.mock('axios', () => ({
  default: {isAxiosError: () => false},
  isAxiosError: () => false,
}));

import {requestPhoneAuthCode, verifyPhoneAuthCode} from '@/features/auth/api/flows';

describe('phone auth flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  describe('requestPhoneAuthCode', () => {
    it('posts national digits with default region and source', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});
      const result = await requestPhoneAuthCode('2025550123');
      expect(mocks.post).toHaveBeenCalledWith('/authn/phone-auth/request-code/', {
        phone_number: '2025550123',
        region: '1-US',
        source: 'login',
      });
      expect(result).toEqual({message: 'sent'});
    });

    it('passes through an explicit source', async () => {
      const challengeId = 'a9a1d853-9687-4199-9f25-d93509e408aa';
      mocks.post.mockResolvedValue({
        data: {message: 'ok', challenge_id: challengeId},
      });
      const result = await requestPhoneAuthCode(
        '2025550123',
        '1-US',
        'subscribe',
      );
      expect(mocks.post).toHaveBeenCalledWith('/authn/phone-auth/request-code/', {
        phone_number: '2025550123',
        region: '1-US',
        source: 'subscribe',
      });
      expect(result.challenge_id).toBe(challengeId);
    });
  });

  describe('verifyPhoneAuthCode', () => {
    it('persists the requested challenge and prefers it during verification', async () => {
      const challengeId = 'a9a1d853-9687-4199-9f25-d93509e408aa';
      const response = {access: 'a', refresh: 'r', user: {phone: '+12025550123', email: ''}};
      mocks.post
        .mockResolvedValueOnce({
          data: {message: 'sent', challenge_id: challengeId},
        })
        .mockResolvedValueOnce({data: response});
      await requestPhoneAuthCode('2025550123');
      const result = await verifyPhoneAuthCode('2025550123', '654321');
      expect(mocks.post).toHaveBeenLastCalledWith('/authn/phone-auth/verify-code/', {
        challenge_id: challengeId,
        region: '1-US',
        code: '654321',
      });
      expect(mocks.persist).toHaveBeenCalledWith(response);
      expect(result).toEqual(response);
    });

    it('falls back to the legacy phone payload when no challenge was returned', async () => {
      const response = {
        access: 'a',
        refresh: 'r',
        user: {phone: '+12025550123', email: ''},
      };
      mocks.post.mockResolvedValue({data: response});

      await verifyPhoneAuthCode('2025550123', '654321');

      expect(mocks.post).toHaveBeenCalledWith('/authn/phone-auth/verify-code/', {
        phone_number: '2025550123',
        region: '1-US',
        code: '654321',
      });
    });

    it('does not persist a session when the verify request fails', async () => {
      mocks.post.mockRejectedValue(new Error('invalid code'));
      await expect(verifyPhoneAuthCode('2025550123', '000000')).rejects.toThrow();
      expect(mocks.persist).not.toHaveBeenCalled();
    });
  });
});
