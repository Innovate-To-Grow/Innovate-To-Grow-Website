import { useCallback, type Dispatch, type SetStateAction } from 'react';

import {
  clearProfileCompletionRequired as clearProfileCompletionRequiredStorage,
  confirmPasswordChange as apiConfirmPasswordChange,
  confirmPasswordReset as apiConfirmPasswordReset,
  type EmailAuthSource,
  getProfile as apiGetProfile,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  type PhoneAuthSource,
  requestEmailAuthCode as apiRequestEmailAuthCode,
  requestLoginCode as apiRequestLoginCode,
  requestPasswordChangeCode as apiRequestPasswordChangeCode,
  requestPasswordReset as apiRequestPasswordReset,
  requestPhoneAuthCode as apiRequestPhoneAuthCode,
  resendRegistrationCode as apiResendRegistrationCode,
  type LoginResponse,
  type User,
  verifyEmailAuthCode as apiVerifyEmailAuthCode,
  verifyPhoneAuthCode as apiVerifyPhoneAuthCode,
  verifyLoginCode as apiVerifyLoginCode,
  verifyPasswordChangeCode as apiVerifyPasswordChangeCode,
  verifyPasswordResetCode as apiVerifyPasswordResetCode,
  verifyRegistrationCode as apiVerifyRegistrationCode,
  getStoredSession,
  updateStoredUser,
} from '@/features/auth/api';

import { dispatchAuthStateChange, getAuthErrorMessage } from './shared';

interface UseAuthActionsProps {
  setUser: Dispatch<SetStateAction<User | null>>;
  setRequiresProfileCompletion: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
}

export function useAuthActions({
  setUser,
  setRequiresProfileCompletion,
  setError,
  setIsLoading,
}: UseAuthActionsProps) {
  const clearError = useCallback(() => {
    setError(null);
  }, [setError]);

  const applyAuthResponse = useCallback(<T extends LoginResponse,>(response: T): T => {
    setUser(response.user);
    setRequiresProfileCompletion(Boolean(response.requires_profile_completion));
    dispatchAuthStateChange();
    return response;
  }, [setRequiresProfileCompletion, setUser]);

  const runWithErrorHandling = useCallback(async <T, >(callback: () => Promise<T>): Promise<T> => {
    setError(null);
    setIsLoading(true);
    try {
      return await callback();
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [setError, setIsLoading]);

  const login = useCallback(async (email: string, password: string) => {
    return runWithErrorHandling(async () => {
      return applyAuthResponse(await apiLogin(email, password));
    });
  }, [applyAuthResponse, runWithErrorHandling]);

  const verifyEmailAuthCode = useCallback(async (email: string, code: string) => {
    return runWithErrorHandling(async () => {
      return applyAuthResponse(await apiVerifyEmailAuthCode(email, code));
    });
  }, [applyAuthResponse, runWithErrorHandling]);

  const verifyLoginCode = useCallback(async (email: string, code: string) => {
    return runWithErrorHandling(async () => {
      return applyAuthResponse(await apiVerifyLoginCode(email, code));
    });
  }, [applyAuthResponse, runWithErrorHandling]);

  const verifyPhoneAuthCode = useCallback(async (phoneNumber: string, code: string, region: string = '1-US', challengeId?: string) => {
    return runWithErrorHandling(async () => {
      return applyAuthResponse(await apiVerifyPhoneAuthCode(phoneNumber, code, region, challengeId));
    });
  }, [applyAuthResponse, runWithErrorHandling]);

  const verifyRegistrationCode = useCallback(async (email: string, code: string) => {
    return runWithErrorHandling(async () => {
      return applyAuthResponse(await apiVerifyRegistrationCode(email, code));
    });
  }, [applyAuthResponse, runWithErrorHandling]);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    setRequiresProfileCompletion(false);
    dispatchAuthStateChange();
  }, [setRequiresProfileCompletion, setUser]);

  const clearProfileCompletionRequirement = useCallback((guard?: {generation: string; refresh?: string}) => {
    if (!clearProfileCompletionRequiredStorage(guard)) return false;
    setRequiresProfileCompletion(false);
    dispatchAuthStateChange();
    return true;
  }, [setRequiresProfileCompletion]);

  const refreshProfile = useCallback(async () => {
    const snapshot = getStoredSession();
    if (!snapshot) return;
    try {
      const profile = await apiGetProfile();
      const updated = updateStoredUser(
        (current) => ({...current, profile_image: profile.profile_image}),
        snapshot.generation,
      );
      if (updated) setUser(updated);
    } catch {
      // User may have been logged out; ignore background refresh failures.
    }
  }, [setUser]);

  return {
    clearError,
    login,
    register: useCallback(async (email: string, password: string, passwordConfirm: string, firstName: string, lastName: string, organization: string, title: string = '') => {
      return runWithErrorHandling(() => apiRegister(email, password, passwordConfirm, firstName, lastName, organization, title));
    }, [runWithErrorHandling]),
    requestEmailAuthCode: useCallback(
      async (email: string, source: EmailAuthSource = 'login', event?: string) =>
        runWithErrorHandling(() => apiRequestEmailAuthCode(email, source, event)),
      [runWithErrorHandling],
    ),
    verifyEmailAuthCode,
    requestPhoneAuthCode: useCallback(
      async (phoneNumber: string, region: string = '1-US', source: PhoneAuthSource = 'login') =>
        runWithErrorHandling(() => apiRequestPhoneAuthCode(phoneNumber, region, source)),
      [runWithErrorHandling],
    ),
    verifyPhoneAuthCode,
    requestLoginCode: useCallback(async (email: string) => runWithErrorHandling(() => apiRequestLoginCode(email)), [runWithErrorHandling]),
    verifyLoginCode,
    verifyRegistrationCode,
    resendRegistrationCode: useCallback(async (email: string) => runWithErrorHandling(() => apiResendRegistrationCode(email)), [runWithErrorHandling]),
    requestPasswordReset: useCallback(async (email: string) => runWithErrorHandling(() => apiRequestPasswordReset(email)), [runWithErrorHandling]),
    verifyPasswordResetCode: useCallback(async (email: string, code: string, challengeId?: string) => runWithErrorHandling(() => apiVerifyPasswordResetCode(email, code, challengeId)), [runWithErrorHandling]),
    confirmPasswordReset: useCallback(async (email: string, verificationToken: string, newPassword: string, confirmPassword: string) => {
      return runWithErrorHandling(() => apiConfirmPasswordReset(email, verificationToken, newPassword, confirmPassword));
    }, [runWithErrorHandling]),
    requestPasswordChangeCode: useCallback(async (email?: string) => runWithErrorHandling(() => apiRequestPasswordChangeCode(email)), [runWithErrorHandling]),
    verifyPasswordChangeCode: useCallback(async (email: string, code: string, challengeId?: string) => runWithErrorHandling(() => apiVerifyPasswordChangeCode(code, email, challengeId)), [runWithErrorHandling]),
    confirmPasswordChange: useCallback(async (verificationToken: string, newPassword: string, confirmPassword: string) => {
      return runWithErrorHandling(() => apiConfirmPasswordChange(verificationToken, newPassword, confirmPassword));
    }, [runWithErrorHandling]),
    logout,
    refreshProfile,
    clearProfileCompletionRequirement,
  };
}
