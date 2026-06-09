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

vi.mock('@/lib/crypto', () => ({
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
  consumeEmailAuthQuery,
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
      expect(mocks.clearProfileCompletion).toHaveBeenCalled();
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

  describe('consumeEmailAuthQuery', () => {
    it('delegates auth, login, and register flows to the matching verifier', async () => {
      mocks.post.mockResolvedValue({data: {access: 'a', refresh: 'r', user: {}}});

      await consumeEmailAuthQuery({flow: 'auth', email: 'a@b.com', code: '111111'});
      await consumeEmailAuthQuery({flow: 'login', email: 'a@b.com', code: '222222'});
      await consumeEmailAuthQuery({flow: 'register', email: 'a@b.com', code: '333333'});

      expect(mocks.post).toHaveBeenNthCalledWith(1, '/authn/email-auth/verify-code/', {
        email: 'a@b.com',
        code: '111111',
      });
      expect(mocks.post).toHaveBeenNthCalledWith(2, '/authn/login/verify-code/', {
        email: 'a@b.com',
        code: '222222',
      });
      expect(mocks.post).toHaveBeenNthCalledWith(3, '/authn/register/verify-code/', {
        email: 'a@b.com',
        code: '333333',
      });
    });
  });

  describe('resendRegistrationCode', () => {
    it('posts to the registration resend endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});

      await expect(resendRegistrationCode('a@b.com')).resolves.toEqual({message: 'sent'});

      expect(mocks.post).toHaveBeenCalledWith('/authn/register/resend-code/', {email: 'a@b.com'});
    });
  });

  describe('requestPasswordReset', () => {
    it('posts to password-reset request endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});
      const result = await requestPasswordReset('a@b.com');
      expect(mocks.post).toHaveBeenCalledWith('/authn/password-reset/request-code/', {email: 'a@b.com'});
      expect(result).toEqual({message: 'sent'});
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

  describe('password change and account deletion flows', () => {
    it('verifies password reset and change codes', async () => {
      mocks.post.mockResolvedValue({data: {verification_token: 'token-1'}});

      await expect(verifyPasswordResetCode('a@b.com', '123456')).resolves.toEqual({verification_token: 'token-1'});
      await expect(verifyPasswordChangeCode('a@b.com', '654321')).resolves.toEqual({verification_token: 'token-1'});

      expect(mocks.post).toHaveBeenNthCalledWith(1, '/authn/password-reset/verify-code/', {
        email: 'a@b.com',
        code: '123456',
      });
      expect(mocks.post).toHaveBeenNthCalledWith(2, '/authn/change-password/verify-code/', {
        email: 'a@b.com',
        code: '654321',
      });
    });

    it('requests and confirms password changes with encrypted passwords', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});

      await requestPasswordChangeCode('a@b.com');
      await confirmPasswordChange('token-1', 'newpw', 'newpw');

      expect(mocks.post).toHaveBeenNthCalledWith(1, '/authn/change-password/request-code/', {email: 'a@b.com'});
      expect(mocks.post).toHaveBeenNthCalledWith(2, '/authn/change-password/confirm/', {
        verification_token: 'token-1',
        new_password: 'enc-pw',
        new_password_confirm: 'enc-pw',
        key_id: 'key-1',
      });
    });

    it('runs account deletion request, verify, and confirm endpoints', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok', verification_token: 'delete-token'}});

      await requestAccountDeletionCode();
      await verifyAccountDeletionCode('123456');
      await confirmAccountDeletion('delete-token');

      expect(mocks.post).toHaveBeenNthCalledWith(1, '/authn/delete-account/request-code/', {});
      expect(mocks.post).toHaveBeenNthCalledWith(2, '/authn/delete-account/verify-code/', {code: '123456'});
      expect(mocks.post).toHaveBeenNthCalledWith(3, '/authn/delete-account/confirm/', {
        verification_token: 'delete-token',
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
});
