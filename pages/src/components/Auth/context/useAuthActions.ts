import { useCallback, type Dispatch, type SetStateAction } from 'react';

import {
  clearProfileCompletionRequired as clearProfileCompletionRequiredStorage,
  confirmPasswordChange as apiConfirmPasswordChange,
  confirmPasswordReset as apiConfirmPasswordReset,
  getProfile as apiGetProfile,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  requestEmailAuthCode as apiRequestEmailAuthCode,
  requestLoginCode as apiRequestLoginCode,
  requestPasswordChangeCode as apiRequestPasswordChangeCode,
  requestPasswordReset as apiRequestPasswordReset,
  resendRegistrationCode as apiResendRegistrationCode,
  type User,
  verifyEmailAuthCode as apiVerifyEmailAuthCode,
  verifyLoginCode as apiVerifyLoginCode,
  verifyPasswordChangeCode as apiVerifyPasswordChangeCode,
  verifyPasswordResetCode as apiVerifyPasswordResetCode,
  verifyRegistrationCode as apiVerifyRegistrationCode,
  isAuthenticated as checkIsAuthenticated,
  updateStoredUser,
} from '../../../services/auth';

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
      const response = await apiLogin(email, password);
      setUser(response.user);
      setRequiresProfileCompletion(false);
      dispatchAuthStateChange();
      return response;
    });
  }, [runWithErrorHandling, setRequiresProfileCompletion, setUser]);

  const verifyEmailAuthCode = useCallback(async (email: string, code: string) => {
    return runWithErrorHandling(async () => {
      const response = await apiVerifyEmailAuthCode(email, code);
      setUser(response.user);
      setRequiresProfileCompletion(response.requires_profile_completion);
      dispatchAuthStateChange();
      return response;
    });
  }, [runWithErrorHandling, setRequiresProfileCompletion, setUser]);

  const verifyLoginCode = useCallback(async (email: string, code: string) => {
    return runWithErrorHandling(async () => {
      const response = await apiVerifyLoginCode(email, code);
      setUser(response.user);
      setRequiresProfileCompletion(false);
      dispatchAuthStateChange();
      return response;
    });
  }, [runWithErrorHandling, setRequiresProfileCompletion, setUser]);

  const verifyRegistrationCode = useCallback(async (email: string, code: string) => {
    return runWithErrorHandling(async () => {
      const response = await apiVerifyRegistrationCode(email, code);
      setUser(response.user);
      setRequiresProfileCompletion(false);
      dispatchAuthStateChange();
      return response;
    });
  }, [runWithErrorHandling, setRequiresProfileCompletion, setUser]);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    setRequiresProfileCompletion(false);
    dispatchAuthStateChange();
  }, [setRequiresProfileCompletion, setUser]);

  const clearProfileCompletionRequirement = useCallback(() => {
    clearProfileCompletionRequiredStorage();
    setRequiresProfileCompletion(false);
    dispatchAuthStateChange();
  }, [setRequiresProfileCompletion]);

  const refreshProfile = useCallback(async () => {
    if (!checkIsAuthenticated()) return;
    try {
      const profile = await apiGetProfile();
      setUser((prev) => {
        if (!prev) return null;
        const nextUser = { ...prev, profile_image: profile.profile_image };
        updateStoredUser(() => nextUser);
        return nextUser;
      });
    } catch {
      // User may have been logged out; ignore background refresh failures.
    }
  }, [setUser]);

  return {
    clearError,
    login,
    register: useCallback(async (email: string, password: string, passwordConfirm: string, firstName: string, lastName: string, organization: string) => {
      return runWithErrorHandling(() => apiRegister(email, password, passwordConfirm, firstName, lastName, organization));
    }, [runWithErrorHandling]),
    requestEmailAuthCode: useCallback(async (email: string) => runWithErrorHandling(() => apiRequestEmailAuthCode(email)), [runWithErrorHandling]),
    verifyEmailAuthCode,
    requestLoginCode: useCallback(async (email: string) => runWithErrorHandling(() => apiRequestLoginCode(email)), [runWithErrorHandling]),
    verifyLoginCode,
    verifyRegistrationCode,
    resendRegistrationCode: useCallback(async (email: string) => runWithErrorHandling(() => apiResendRegistrationCode(email)), [runWithErrorHandling]),
    requestPasswordReset: useCallback(async (email: string) => runWithErrorHandling(() => apiRequestPasswordReset(email)), [runWithErrorHandling]),
    verifyPasswordResetCode: useCallback(async (email: string, code: string) => runWithErrorHandling(() => apiVerifyPasswordResetCode(email, code)), [runWithErrorHandling]),
    confirmPasswordReset: useCallback(async (email: string, verificationToken: string, newPassword: string, confirmPassword: string) => {
      return runWithErrorHandling(() => apiConfirmPasswordReset(email, verificationToken, newPassword, confirmPassword));
    }, [runWithErrorHandling]),
    requestPasswordChangeCode: useCallback(async (email: string) => runWithErrorHandling(() => apiRequestPasswordChangeCode(email)), [runWithErrorHandling]),
    verifyPasswordChangeCode: useCallback(async (email: string, code: string) => runWithErrorHandling(() => apiVerifyPasswordChangeCode(email, code)), [runWithErrorHandling]),
    confirmPasswordChange: useCallback(async (verificationToken: string, newPassword: string, confirmPassword: string) => {
      return runWithErrorHandling(() => apiConfirmPasswordChange(verificationToken, newPassword, confirmPassword));
    }, [runWithErrorHandling]),
    logout,
    refreshProfile,
    clearProfileCompletionRequirement,
  };
}
