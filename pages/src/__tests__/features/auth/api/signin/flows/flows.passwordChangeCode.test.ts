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
  confirmAccountDeletion,
  confirmPasswordChange,
  requestAccountDeletionCode,
  requestPasswordChangeCode,
  resendRegistrationCode,
  verifyAccountDeletionCode,
  verifyPasswordChangeCode,
} from '@/features/auth/api/signin/flows';

describe('auth flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.encrypt.mockResolvedValue({encryptedPassword: 'enc-pw', keyId: 'key-1'});
  });

  describe('password change code (channel-aware)', () => {
    it('omits email for phone-only accounts and surfaces the SMS channel', async () => {
      const challengeId = 'c742ef5b-e34f-491d-91f2-8ead9bc10401';
      mocks.post.mockResolvedValue({data: {message: 'Verification code sent.', channel: 'sms', destination: '(•••) •••-4567', challenge_id: challengeId}});

      const result = await requestPasswordChangeCode();

      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/change-password/request-code/',
        expect.objectContaining({
          verification_challenge_id: expect.any(String),
        }),
      );
      expect(result.channel).toBe('sms');
      expect(result.destination).toBe('(•••) •••-4567');
      expect(result.challenge_id).toBe(challengeId);
    });

    it('includes the email when one is supplied (disambiguation)', async () => {
      mocks.post.mockResolvedValue({data: {message: 'Verification code sent.', channel: 'email'}});

      await requestPasswordChangeCode('a@b.com');

      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/change-password/request-code/',
        expect.objectContaining({email: 'a@b.com'}),
      );
    });

    it('passes the persisted challenge when verifying an SMS password-change code', async () => {
      const challengeId = 'c742ef5b-e34f-491d-91f2-8ead9bc10401';
      mocks.post
        .mockResolvedValueOnce({
          data: {
            message: 'Verification code sent.',
            channel: 'sms',
            challenge_id: challengeId,
          },
        })
        .mockResolvedValueOnce({data: {message: 'ok', verification_token: 'tok'}});

      await requestPasswordChangeCode();
      await verifyPasswordChangeCode('123456');

      expect(mocks.post).toHaveBeenLastCalledWith('/authn/change-password/verify-code/', {
        code: '123456',
        challenge_id: challengeId,
      });
    });

    it('keeps the legacy code-only verification payload without a challenge', async () => {
      mocks.post.mockResolvedValue({
        data: {message: 'ok', verification_token: 'tok'},
      });

      await verifyPasswordChangeCode('123456');

      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/change-password/verify-code/',
        {code: '123456'},
      );
    });
  });

  describe('resendRegistrationCode', () => {
    it('posts email to the resend endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'resent'}});
      const result = await resendRegistrationCode('a@b.com');
      expect(mocks.post).toHaveBeenCalledWith('/authn/register/resend-code/', expect.objectContaining({
        email: 'a@b.com', verification_payload: 'test-altcha-payload',
      }));
      expect(result).toEqual({message: 'resent'});
    });
  });

  describe('confirmPasswordChange', () => {
    it('encrypts the new password and posts to the confirm endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'done'}});

      await confirmPasswordChange('token-123', 'newpw', 'newpw');

      expect(mocks.encrypt).toHaveBeenCalledTimes(2);
      expect(mocks.post).toHaveBeenCalledWith('/authn/change-password/confirm/', {
        verification_token: 'token-123',
        new_password: 'enc-pw',
        new_password_confirm: 'enc-pw',
        key_id: 'key-1',
      });
    });
  });

  describe('account deletion', () => {
    it('requests a deletion code', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});
      const result = await requestAccountDeletionCode();
      expect(mocks.post).toHaveBeenCalledWith('/authn/delete-account/request-code/', {
        verification_challenge_id: '11111111-1111-4111-8111-111111111111',
        verification_payload: 'test-altcha-payload',
        send_request_id: '22222222-2222-4222-8222-222222222222',
      });
      expect(result).toEqual({message: 'sent'});
    });

    it('verifies a deletion code', async () => {
      mocks.post.mockResolvedValue({data: {verification_token: 'del-token'}});
      const result = await verifyAccountDeletionCode('123456');
      expect(mocks.post).toHaveBeenCalledWith('/authn/delete-account/verify-code/', {code: '123456'});
      expect(result).toEqual({verification_token: 'del-token'});
    });

    it('confirms account deletion', async () => {
      mocks.post.mockResolvedValue({data: {message: 'deleted'}});
      const result = await confirmAccountDeletion('del-token');
      expect(mocks.post).toHaveBeenCalledWith('/authn/delete-account/confirm/', {verification_token: 'del-token'});
      expect(result).toEqual({message: 'deleted'});
    });
  });
});
