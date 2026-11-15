import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  encrypt: vi.fn(),
  clearKeyCache: vi.fn(),
  persist: vi.fn(),
  clearProfileCompletion: vi.fn(),
}));

vi.mock('@/features/auth/api/session/client', () => ({
  authApi: {post: mocks.post},
}));

vi.mock('@/lib/security', () => ({
  encryptPasswordWithCurrentKey: mocks.encrypt,
  clearKeyCache: mocks.clearKeyCache,
}));

vi.mock('@/features/auth/api/session/storage', () => ({
  persistAuthSession: mocks.persist,
  clearProfileCompletionRequired: mocks.clearProfileCompletion,
}));

vi.mock('axios', () => ({
  default: {isAxiosError: (e: unknown) => e && typeof e === 'object' && 'isAxiosError' in e},
  isAxiosError: (e: unknown) => e && typeof e === 'object' && 'isAxiosError' in e,
}));

import {
  confirmPasswordReset,
  requestPasswordReset,
  verifyEmailAuthCode,
  verifyPasswordResetCode,
  verifyRegistrationCode,
} from '@/features/auth/api/signin/flows';

describe('auth flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.encrypt.mockResolvedValue({encryptedPassword: 'enc-pw', keyId: 'key-1'});
  });

  describe('verifyEmailAuthCode', () => {
    it('persists session on success', async () => {
      const response = {access: 'a', refresh: 'r', user: {}};
      mocks.post.mockResolvedValue({data: response});

      await verifyEmailAuthCode('a@b.com', '654321');
      // The emailed-link exchange must not carry the browser's stored session.
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/email-auth/verify-code/',
        {email: 'a@b.com', code: '654321'},
        {skipAuth: true},
      );
      expect(mocks.persist).toHaveBeenCalledWith(response);
    });
  });

  describe('verifyRegistrationCode', () => {
    it('persists session on success', async () => {
      const response = {access: 'a', refresh: 'r', user: {}};
      mocks.post.mockResolvedValue({data: response});

      await verifyRegistrationCode('a@b.com', '111222');
      expect(mocks.post).toHaveBeenCalledWith('/authn/register/verify-code/', {email: 'a@b.com', code: '111222'});
      expect(mocks.persist).toHaveBeenCalledWith(response);
    });
  });

  describe('requestPasswordReset', () => {
    it('persists the opaque challenge and passes it to verification', async () => {
      const challengeId = 'f34d515f-cb90-43b4-acd0-246554abdaaa';
      mocks.post
        .mockResolvedValueOnce({
          data: {message: 'sent', challenge_id: challengeId},
        })
        .mockResolvedValueOnce({
          data: {message: 'verified', verification_token: 'reset-token'},
        });

      const result = await requestPasswordReset('a@b.com');

      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/password-reset/request-code/',
        expect.objectContaining({email: 'a@b.com'}),
      );
      expect(result).toEqual({message: 'sent', challenge_id: challengeId});

      await verifyPasswordResetCode('a@b.com', '123456');

      expect(mocks.post).toHaveBeenLastCalledWith(
        '/authn/password-reset/verify-code/',
        {
          email: 'a@b.com',
          code: '123456',
          challenge_id: challengeId,
        },
      );
    });

    it('keeps the legacy verify payload when the response omits a challenge', async () => {
      mocks.post
        .mockResolvedValueOnce({data: {message: 'sent'}})
        .mockResolvedValueOnce({
          data: {message: 'verified', verification_token: 'reset-token'},
        });

      await requestPasswordReset('legacy@example.com');
      await verifyPasswordResetCode('legacy@example.com', '654321');

      expect(mocks.post).toHaveBeenLastCalledWith(
        '/authn/password-reset/verify-code/',
        {email: 'legacy@example.com', code: '654321'},
      );
    });
  });

  describe('confirmPasswordReset', () => {
    it('encrypts new password and posts to confirm endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'done'}});

      await confirmPasswordReset('a@b.com', 'token-123', 'newpw', 'newpw');

      expect(mocks.encrypt).toHaveBeenCalledTimes(2);
      expect(mocks.post).toHaveBeenCalledWith('/authn/password-reset/confirm/', {
        email: 'a@b.com',
        verification_token: 'token-123',
        new_password: 'enc-pw',
        new_password_confirm: 'enc-pw',
        key_id: 'key-1',
      });
    });
  });
});
