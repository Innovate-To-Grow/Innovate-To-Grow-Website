import { useCallback, useMemo } from 'react';

import {
  type EmailAuthSource,
  login as apiLogin,
  register as apiRegister,
  type PhoneAuthSource,
  requestEmailAuthCode as apiRequestEmailAuthCode,
  requestLoginCode as apiRequestLoginCode,
  requestPhoneAuthCode as apiRequestPhoneAuthCode,
  resendRegistrationCode as apiResendRegistrationCode,
  verifyEmailAuthCode as apiVerifyEmailAuthCode,
  verifyPhoneAuthCode as apiVerifyPhoneAuthCode,
  verifyLoginCode as apiVerifyLoginCode,
  verifyRegistrationCode as apiVerifyRegistrationCode,
} from '@/features/auth/api';

import type { AuthRequest } from './useAuthRequest';

/** Signing in or registering: password, emailed code, SMS code, and the registration code. */
export function useSignInActions({ applyAuthResponse, runWithErrorHandling }: AuthRequest) {
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

  const register = useCallback(async (email: string, password: string, passwordConfirm: string, firstName: string, lastName: string, organization: string, title: string = '') => {
    return runWithErrorHandling(() => apiRegister(email, password, passwordConfirm, firstName, lastName, organization, title));
  }, [runWithErrorHandling]);
  const requestEmailAuthCode = useCallback(
    async (email: string, source: EmailAuthSource = 'login', event?: string) =>
      runWithErrorHandling(() => apiRequestEmailAuthCode(email, source, event)),
    [runWithErrorHandling],
  );
  const requestPhoneAuthCode = useCallback(
    async (phoneNumber: string, region: string = '1-US', source: PhoneAuthSource = 'login') =>
      runWithErrorHandling(() => apiRequestPhoneAuthCode(phoneNumber, region, source)),
    [runWithErrorHandling],
  );
  const requestLoginCode = useCallback(async (email: string) => runWithErrorHandling(() => apiRequestLoginCode(email)), [runWithErrorHandling]);
  const resendRegistrationCode = useCallback(async (email: string) => runWithErrorHandling(() => apiResendRegistrationCode(email)), [runWithErrorHandling]);

  return useMemo(
    () => ({
      login,
      register,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
      requestLoginCode,
      verifyLoginCode,
      verifyRegistrationCode,
      resendRegistrationCode,
    }),
    [
      login,
      register,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
      requestLoginCode,
      verifyLoginCode,
      verifyRegistrationCode,
      resendRegistrationCode,
    ],
  );
}
