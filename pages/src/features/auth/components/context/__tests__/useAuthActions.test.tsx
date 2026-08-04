import {act, renderHook} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

const verifyPasswordChangeCode = vi.hoisted(() => vi.fn());

vi.mock('@/features/auth/api', () => ({
  clearProfileCompletionRequired: vi.fn(),
  confirmPasswordChange: vi.fn(),
  confirmPasswordReset: vi.fn(),
  getProfile: vi.fn(),
  getStoredSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  requestEmailAuthCode: vi.fn(),
  requestLoginCode: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  requestPasswordReset: vi.fn(),
  requestPhoneAuthCode: vi.fn(),
  resendRegistrationCode: vi.fn(),
  updateStoredUser: vi.fn(),
  verifyEmailAuthCode: vi.fn(),
  verifyLoginCode: vi.fn(),
  verifyPasswordChangeCode,
  verifyPasswordResetCode: vi.fn(),
  verifyPhoneAuthCode: vi.fn(),
  verifyRegistrationCode: vi.fn(),
}));

import {useAuthActions} from '../useAuthActions';

describe('useAuthActions', () => {
  it('adapts the context email/code order to the code/email API order', async () => {
    verifyPasswordChangeCode.mockResolvedValue({
      message: 'ok',
      verification_token: 'verification-token',
    });
    const setters = {
      setUser: vi.fn(),
      setRequiresProfileCompletion: vi.fn(),
      setError: vi.fn(),
      setIsLoading: vi.fn(),
    };
    const {result} = renderHook(() => useAuthActions(setters));

    await act(async () => {
      await result.current.verifyPasswordChangeCode(
        'member@example.com',
        '123456',
        'c742ef5b-e34f-491d-91f2-8ead9bc10401',
      );
    });

    expect(verifyPasswordChangeCode).toHaveBeenCalledWith(
      '123456',
      'member@example.com',
      'c742ef5b-e34f-491d-91f2-8ead9bc10401',
    );
  });
});
