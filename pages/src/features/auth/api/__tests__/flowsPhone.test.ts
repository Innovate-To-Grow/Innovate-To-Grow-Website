import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  persist: vi.fn(),
  clearProfileCompletion: vi.fn(),
}));

vi.mock('../client', () => ({
  authApi: {post: mocks.post},
}));

vi.mock('@/lib/crypto', () => ({
  encryptPasswordWithCurrentKey: vi.fn(),
  clearKeyCache: vi.fn(),
}));

vi.mock('../storage', () => ({
  persistAuthSession: mocks.persist,
  clearProfileCompletionRequired: mocks.clearProfileCompletion,
}));

vi.mock('axios', () => ({
  default: {isAxiosError: () => false},
  isAxiosError: () => false,
}));

import {requestPhoneAuthCode, verifyPhoneAuthCode} from '../flows';

describe('phone auth flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
      mocks.post.mockResolvedValue({data: {message: 'ok'}});
      await requestPhoneAuthCode('2025550123', '1-US', 'subscribe');
      expect(mocks.post).toHaveBeenCalledWith('/authn/phone-auth/request-code/', {
        phone_number: '2025550123',
        region: '1-US',
        source: 'subscribe',
      });
    });
  });

  describe('verifyPhoneAuthCode', () => {
    it('posts the code and persists the session on success', async () => {
      const response = {access: 'a', refresh: 'r', user: {phone: '+12025550123', email: ''}};
      mocks.post.mockResolvedValue({data: response});
      const result = await verifyPhoneAuthCode('2025550123', '654321');
      expect(mocks.post).toHaveBeenCalledWith('/authn/phone-auth/verify-code/', {
        phone_number: '2025550123',
        region: '1-US',
        code: '654321',
      });
      expect(mocks.persist).toHaveBeenCalledWith(response);
      expect(result).toEqual(response);
    });
  });
});
