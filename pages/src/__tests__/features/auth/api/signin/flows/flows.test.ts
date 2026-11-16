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
  login,
  register,
  requestEmailAuthCode,
  requestLoginCode,
  verifyLoginCode,
} from '@/features/auth/api/signin/flows';

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
      expect(mocks.post).toHaveBeenCalled();
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
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/login/request-code/',
        expect.objectContaining({email: 'a@b.com'}),
      );
      expect(result).toEqual({message: 'sent'});
    });
  });

  describe('requestEmailAuthCode', () => {
    it('posts email and source', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com', 'login');
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/email-auth/request-code/',
        expect.objectContaining({email: 'a@b.com', source: 'login'}),
      );
    });

    it('defaults source to login', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com');
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/email-auth/request-code/',
        expect.objectContaining({email: 'a@b.com', source: 'login'}),
      );
    });

    it('includes the event slug when provided', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com', 'event_registration', 'demo-day');
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/email-auth/request-code/',
        expect.objectContaining({
          email: 'a@b.com',
          source: 'event_registration',
          event: 'demo-day',
        }),
      );
    });

    it('omits the event key when no event is given', async () => {
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestEmailAuthCode('a@b.com', 'event_registration');
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/email-auth/request-code/',
        expect.objectContaining({
          email: 'a@b.com',
          source: 'event_registration',
        }),
      );
    });
  });

  describe('verifyLoginCode', () => {
    it('persists session on success', async () => {
      const response = {access: 'a', refresh: 'r', user: {}};
      mocks.post.mockResolvedValue({data: response});

      await verifyLoginCode('a@b.com', '123456');
      // The emailed code is the credential: the browser's stored session (a
      // stale one, on /login-link) must not ride along.
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/login/verify-code/',
        {email: 'a@b.com', code: '123456'},
        {skipAuth: true},
      );
      expect(mocks.persist).toHaveBeenCalledWith(response);
    });
  });
});
