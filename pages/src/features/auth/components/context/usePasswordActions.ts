import { useCallback, useMemo } from 'react';

import {
  confirmPasswordChange as apiConfirmPasswordChange,
  confirmPasswordReset as apiConfirmPasswordReset,
  requestPasswordChangeCode as apiRequestPasswordChangeCode,
  requestPasswordReset as apiRequestPasswordReset,
  verifyPasswordChangeCode as apiVerifyPasswordChangeCode,
  verifyPasswordResetCode as apiVerifyPasswordResetCode,
} from '@/features/auth/api';

import type { AuthRequest } from './useAuthRequest';

/** Password reset (signed out) and password change (signed in). */
export function usePasswordActions({ runWithErrorHandling }: AuthRequest) {
  const requestPasswordReset = useCallback(async (email: string) => runWithErrorHandling(() => apiRequestPasswordReset(email)), [runWithErrorHandling]);
  const verifyPasswordResetCode = useCallback(async (email: string, code: string, challengeId?: string) => runWithErrorHandling(() => apiVerifyPasswordResetCode(email, code, challengeId)), [runWithErrorHandling]);
  const confirmPasswordReset = useCallback(async (email: string, verificationToken: string, newPassword: string, confirmPassword: string) => {
    return runWithErrorHandling(() => apiConfirmPasswordReset(email, verificationToken, newPassword, confirmPassword));
  }, [runWithErrorHandling]);
  const requestPasswordChangeCode = useCallback(async (email?: string) => runWithErrorHandling(() => apiRequestPasswordChangeCode(email)), [runWithErrorHandling]);
  const verifyPasswordChangeCode = useCallback(async (email: string, code: string, challengeId?: string) => runWithErrorHandling(() => apiVerifyPasswordChangeCode(code, email, challengeId)), [runWithErrorHandling]);
  const confirmPasswordChange = useCallback(async (verificationToken: string, newPassword: string, confirmPassword: string) => {
    return runWithErrorHandling(() => apiConfirmPasswordChange(verificationToken, newPassword, confirmPassword));
  }, [runWithErrorHandling]);

  return useMemo(
    () => ({
      requestPasswordReset,
      verifyPasswordResetCode,
      confirmPasswordReset,
      requestPasswordChangeCode,
      verifyPasswordChangeCode,
      confirmPasswordChange,
    }),
    [
      requestPasswordReset,
      verifyPasswordResetCode,
      confirmPasswordReset,
      requestPasswordChangeCode,
      verifyPasswordChangeCode,
      confirmPasswordChange,
    ],
  );
}
