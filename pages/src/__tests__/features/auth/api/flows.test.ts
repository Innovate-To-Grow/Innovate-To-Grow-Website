import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  encrypt: vi.fn(),
  clearKeyCache: vi.fn(),
  persist: vi.fn(),
  clearProfileCompletion: vi.fn(),
}));

vi.mock('@/features/auth/api/client', () => ({
  authApi: {post: mocks.post},
}));

vi.mock('@/lib/security', () => ({
  encryptPasswordWithCurrentKey: mocks.encrypt,
  clearKeyCache: mocks.clearKeyCache,
}));

vi.mock('@/features/auth/api/storage', () => ({
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
  confirmPasswordReset,
  login,
  register,
  requestAccountDeletionCode,
  requestEmailAuthCode,
  requestLoginCode,
  requestPasswordChangeCode,
  requestPasswordReset,
  resendRegistrationCode,
  subscribe,
  verifyAccountDeletionCode,
  verifyEmailAuthCode,
  verifyLoginCode,
  verifyPasswordChangeCode,
  verifyPasswordResetCode,
  verifyRegistrationCode,
} from '@/features/auth/api/flows';

describe('auth flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.encrypt.mockResolvedValue({encryptedPassword: 'enc-pw', keyId: 'key-1'});
  });

  describe('register', () => {
    it('encrypts passwords and posts to register endpoint', async () => {
      mocks.post.mockResolvedValue({data: {access: 'a', refresh: 'r', user: {}}});

      await register('a@b.com', 'pw', 'pw', 'First', 'Last', 'Org', 'Title');

      expect(mocks.encrypt).toHaveBeenCalledTimes(2);
      expect(mocks.post).toHaveBeenCalledWith('/authn/register/', expect.objectContaining({
        email: 'a@b.com',
        password: 'enc-pw',
        password_confirm: 'enc-pw',
        key_id: 'key-1',
        first_name: 'First',
        last_name: 'Last',
        organization: 'Org',
        title: 'Title',
      }));
      expect(mocks.clearProfileCompletion).not.toHaveBeenCalled();
    });

    it('clears key cache on encryption failure', async () => {
      const axiosError = {isAxiosError: true, response: {data: 'public_key invalid'}};
      mocks.post.mockRejectedValue(axiosError);

      await expect(register('a@b.com', 'pw', 'pw', 'F', 'L', 'O')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).toHaveBeenCalled();
    });
  });

  describe('login', () => {
    it('encrypts password and persists session on success', async () => {
      const loginResponse = {access: 'tok', refresh: 'ref', user: {id: '1'}};
      mocks.post.mockResolvedValue({data: loginResponse});

      const result = await login('a@b.com', 'password');

      expect(mocks.encrypt).toHaveBeenCalledWith('password');
      expect(mocks.post).toHaveBeenCalledWith('/authn/login/', {
        email: 'a@b.com',
        password: 'enc-pw',
        key_id: 'key-1',
      });
      expect(mocks.persist).toHaveBeenCalledWith(loginResponse);
      expect(result).toEqual(loginResponse);
    });

    it('clears key cache on decryption error response', async () => {
      const axiosError = {isAxiosError: true, response: {data: 'decrypt failed'}};
      mocks.post.mockRejectedValue(axiosError);

      await expect(login('a@b.com', 'pw')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).toHaveBeenCalled();
    });
  });

  describe('requestLoginCode', () => {
    it('posts email to request-code endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});
      const result = await requestLoginCode('a@b.com');
      expect(mocks.post).toHaveBeenCalledWith('/authn/login/request-code/', {email: 'a@b.com'});
      expect(result).toEqual({message: 'sent'});
    });
  });

  describe('requestEmailAuthCode', () => {
    it('posts email and source', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com', 'login');
      expect(mocks.post).toHaveBeenCalledWith('/authn/email-auth/request-code/', {email: 'a@b.com', source: 'login'});
    });

    it('defaults source to login', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com');
      expect(mocks.post).toHaveBeenCalledWith('/authn/email-auth/request-code/', {email: 'a@b.com', source: 'login'});
    });

    it('includes the event slug when provided', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com', 'event_registration', 'demo-day');
      expect(mocks.post).toHaveBeenCalledWith('/authn/email-auth/request-code/', {
        email: 'a@b.com',
        source: 'event_registration',
        event: 'demo-day',
      });
    });

    it('omits the event key when no event is given', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com', 'event_registration');
      expect(mocks.post).toHaveBeenCalledWith('/authn/email-auth/request-code/', {
        email: 'a@b.com',
        source: 'event_registration',
      });
    });
  });

  describe('verifyLoginCode', () => {
    it('persists session on success', async () => {
      const response = {access: 'a', refresh: 'r', user: {}};
      mocks.post.mockResolvedValue({data: response});

      await verifyLoginCode('a@b.com', '123456');
      expect(mocks.post).toHaveBeenCalledWith('/authn/login/verify-code/', {email: 'a@b.com', code: '123456'});
      expect(mocks.persist).toHaveBeenCalledWith(response);
    });
  });

  describe('verifyEmailAuthCode', () => {
    it('persists session on success', async () => {
      const response = {access: 'a', refresh: 'r', user: {}};
      mocks.post.mockResolvedValue({data: response});

      await verifyEmailAuthCode('a@b.com', '654321');
      expect(mocks.post).toHaveBeenCalledWith('/authn/email-auth/verify-code/', {email: 'a@b.com', code: '654321'});
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

      expect(mocks.post).toHaveBeenCalledWith('/authn/password-reset/request-code/', {email: 'a@b.com'});
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

  describe('subscribe', () => {
    it('posts email to subscribe endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'subscribed'}});
      const result = await subscribe('a@b.com');
      expect(mocks.post).toHaveBeenCalledWith('/authn/subscribe/', {email: 'a@b.com'});
      expect(result).toEqual({message: 'subscribed'});
    });
  });

  describe('password change code (channel-aware)', () => {
    it('omits email for phone-only accounts and surfaces the SMS channel', async () => {
      const challengeId = 'c742ef5b-e34f-491d-91f2-8ead9bc10401';
      mocks.post.mockResolvedValue({data: {message: 'Verification code sent.', channel: 'sms', destination: '(•••) •••-4567', challenge_id: challengeId}});

      const result = await requestPasswordChangeCode();

      expect(mocks.post).toHaveBeenCalledWith('/authn/change-password/request-code/', {});
      expect(result.channel).toBe('sms');
      expect(result.destination).toBe('(•••) •••-4567');
      expect(result.challenge_id).toBe(challengeId);
    });

    it('includes the email when one is supplied (disambiguation)', async () => {
      mocks.post.mockResolvedValue({data: {message: 'Verification code sent.', channel: 'email'}});

      await requestPasswordChangeCode('a@b.com');

      expect(mocks.post).toHaveBeenCalledWith('/authn/change-password/request-code/', {email: 'a@b.com'});
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
      expect(mocks.post).toHaveBeenCalledWith('/authn/register/resend-code/', {email: 'a@b.com'});
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
      expect(mocks.post).toHaveBeenCalledWith('/authn/delete-account/request-code/', {});
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

  describe('encryption failure detection', () => {
    it('clears the key cache for a non-axios error', async () => {
      mocks.post.mockRejectedValue(new Error('crypto failure'));

      await expect(login('a@b.com', 'pw')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).toHaveBeenCalled();
    });

    it('does not clear the key cache for a falsy rejection', async () => {
      mocks.post.mockRejectedValue(null);

      await expect(login('a@b.com', 'pw')).rejects.toBeNull();
      expect(mocks.clearKeyCache).not.toHaveBeenCalled();
    });

    it('clears the key cache for an axios error with an object payload mentioning the key', async () => {
      const axiosError = {isAxiosError: true, response: {data: {key_id: 'stale-key'}}};
      mocks.post.mockRejectedValue(axiosError);

      await expect(register('a@b.com', 'pw', 'pw', 'F', 'L', 'O')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).toHaveBeenCalled();
    });

    it('does not clear the key cache for an axios error without matching content', async () => {
      const axiosError = {isAxiosError: true, response: {}};
      mocks.post.mockRejectedValue(axiosError);

      await expect(register('a@b.com', 'pw', 'pw', 'F', 'L', 'O')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).not.toHaveBeenCalled();
    });
  });
});
