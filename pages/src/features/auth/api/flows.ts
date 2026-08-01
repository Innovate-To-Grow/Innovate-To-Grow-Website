import axios from 'axios';

import { clearKeyCache, encryptPasswordWithCurrentKey } from '@/lib/crypto';
import { authApi } from './client';
import {persistAuthSession} from './storage';
import type {
  EmailAuthFlow,
  EmailAuthRequestResponse,
  EmailAuthSource,
  EmailAuthVerifyResponse,
  LoginResponse,
  MessageResponse,
  PasswordChangeRequestResponse,
  PhoneAuthRequestResponse,
  PhoneAuthSource,
  RegisterResponse,
  SmsChallengeResponse,
  VerificationTokenResponse,
} from './types';
import {
  forgetSmsChallenge,
  passwordChangeChallengeScope,
  passwordResetChallengeScope,
  phoneAuthChallengeScope,
  readSmsChallenge,
  rememberSmsChallenge,
} from './smsChallenges';

const isEncryptionFailure = (error: unknown): boolean => {
  if (!error) return false;
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data;
    const flat = typeof payload === 'string' ? payload : JSON.stringify(payload ?? '');
    return /decrypt|key_id|public[-_]key/i.test(flat);
  }
  // Web Crypto throws a DOMException with no specific message on decryption
  // failure. Conservatively clear the cache on any non-axios encryption error
  // so the next attempt re-fetches a fresh key.
  return error instanceof Error;
};

export const register = async (
  email: string,
  password: string,
  passwordConfirm: string,
  firstName: string,
  lastName: string,
  organization: string,
  title: string = '',
): Promise<RegisterResponse> => {
  try {
    const { encryptedPassword, keyId } = await encryptPasswordWithCurrentKey(password);
    const { encryptedPassword: encryptedConfirm } = await encryptPasswordWithCurrentKey(passwordConfirm);
    const response = await authApi.post<RegisterResponse>('/authn/register/', {
      email,
      password: encryptedPassword,
      password_confirm: encryptedConfirm,
      key_id: keyId,
      first_name: firstName,
      last_name: lastName,
      organization,
      title,
    });
    return response.data;
  } catch (error) {
    if (isEncryptionFailure(error)) {
      clearKeyCache();
    }
    throw error;
  }
};

export const login = async (email: string, password: string): Promise<LoginResponse> => {
  try {
    const { encryptedPassword, keyId } = await encryptPasswordWithCurrentKey(password);
    const response = await authApi.post<LoginResponse>('/authn/login/', {
      email,
      password: encryptedPassword,
      key_id: keyId,
    });
    persistAuthSession(response.data);
    return response.data;
  } catch (error) {
    if (isEncryptionFailure(error)) {
      clearKeyCache();
    }
    throw error;
  }
};

export const requestLoginCode = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/login/request-code/', { email });
  return response.data;
};

export const requestEmailAuthCode = async (
  email: string,
  source: EmailAuthSource = 'login',
  event?: string,
): Promise<EmailAuthRequestResponse> => {
  const response = await authApi.post<EmailAuthRequestResponse>('/authn/email-auth/request-code/', {
    email,
    source,
    ...(event ? {event} : {}),
  });
  return response.data;
};

export const verifyLoginCode = async (email: string, code: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/login/verify-code/', { email, code });
  persistAuthSession(response.data);
  return response.data;
};

export const verifyEmailAuthCode = async (email: string, code: string): Promise<EmailAuthVerifyResponse> => {
  const response = await authApi.post<EmailAuthVerifyResponse>('/authn/email-auth/verify-code/', { email, code });
  persistAuthSession(response.data);
  return response.data;
};

export const requestPhoneAuthCode = async (
  phoneNumber: string,
  region: string = '1-US',
  source: PhoneAuthSource = 'login',
): Promise<PhoneAuthRequestResponse> => {
  const response = await authApi.post<PhoneAuthRequestResponse>('/authn/phone-auth/request-code/', {
    phone_number: phoneNumber,
    region,
    source,
  });
  rememberSmsChallenge(
    phoneAuthChallengeScope(phoneNumber, region),
    response.data.challenge_id,
  );
  return response.data;
};

export const verifyPhoneAuthCode = async (
  phoneNumber: string,
  code: string,
  region: string = '1-US',
  challengeId?: string,
): Promise<EmailAuthVerifyResponse> => {
  const scope = phoneAuthChallengeScope(phoneNumber, region);
  const resolvedChallengeId = challengeId ?? readSmsChallenge(scope);
  const response = await authApi.post<EmailAuthVerifyResponse>('/authn/phone-auth/verify-code/', {
    ...(resolvedChallengeId
      ? {challenge_id: resolvedChallengeId}
      : {phone_number: phoneNumber}),
    region,
    code,
  });
  forgetSmsChallenge(scope, resolvedChallengeId);
  persistAuthSession(response.data);
  return response.data;
};

export const verifyRegistrationCode = async (email: string, code: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/register/verify-code/', { email, code });
  persistAuthSession(response.data);
  return response.data;
};

export const consumeEmailAuthQuery = async ({
  flow,
  email,
  code,
}: {
  flow: EmailAuthFlow;
  email: string;
  code: string;
}): Promise<LoginResponse | EmailAuthVerifyResponse> => {
  if (flow === 'auth') {
    return verifyEmailAuthCode(email, code);
  }
  if (flow === 'login') {
    return verifyLoginCode(email, code);
  }
  return verifyRegistrationCode(email, code);
};

export const resendRegistrationCode = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/register/resend-code/', { email });
  return response.data;
};

export const requestPasswordReset = async (
  email: string,
): Promise<SmsChallengeResponse> => {
  const response = await authApi.post<SmsChallengeResponse>(
    '/authn/password-reset/request-code/',
    {email},
  );
  // The public endpoint deliberately has the same response shape for email,
  // phone, and unknown identifiers. Persist any opaque challenge returned; the
  // email verifier safely ignores it, while SMS verification requires it.
  rememberSmsChallenge(
    passwordResetChallengeScope(email),
    response.data.challenge_id,
  );
  return response.data;
};

export const verifyPasswordResetCode = async (
  email: string,
  code: string,
  challengeId?: string,
): Promise<VerificationTokenResponse> => {
  const scope = passwordResetChallengeScope(email);
  const resolvedChallengeId = challengeId ?? readSmsChallenge(scope);
  const response = await authApi.post<VerificationTokenResponse>(
    '/authn/password-reset/verify-code/',
    {
      email,
      code,
      ...(resolvedChallengeId ? {challenge_id: resolvedChallengeId} : {}),
    },
  );
  forgetSmsChallenge(scope, resolvedChallengeId);
  return response.data;
};

export const confirmPasswordReset = async (
  email: string,
  verificationToken: string,
  newPassword: string,
  confirmPassword: string,
): Promise<MessageResponse> => {
  const { encryptedPassword, keyId } = await encryptPasswordWithCurrentKey(newPassword);
  const { encryptedPassword: encryptedConfirm } = await encryptPasswordWithCurrentKey(confirmPassword);
  const response = await authApi.post<MessageResponse>('/authn/password-reset/confirm/', {
    email,
    verification_token: verificationToken,
    new_password: encryptedPassword,
    new_password_confirm: encryptedConfirm,
    key_id: keyId,
  });
  return response.data;
};

export const requestPasswordChangeCode = async (email?: string): Promise<PasswordChangeRequestResponse> => {
  // Omit `email` entirely for phone-only accounts; the backend then selects the
  // verification channel (verified email, else SMS) and reports it in the response.
  const response = await authApi.post<PasswordChangeRequestResponse>(
    '/authn/change-password/request-code/',
    email ? { email } : {},
  );
  rememberSmsChallenge(
    passwordChangeChallengeScope(email),
    response.data.channel === 'sms' ? response.data.challenge_id : undefined,
  );
  return response.data;
};

export const verifyPasswordChangeCode = async (
  code: string,
  email?: string,
  challengeId?: string,
): Promise<VerificationTokenResponse> => {
  const scope = passwordChangeChallengeScope(email);
  const resolvedChallengeId = challengeId ?? readSmsChallenge(scope);
  const response = await authApi.post<VerificationTokenResponse>(
    '/authn/change-password/verify-code/',
    {
      ...(email ? {email} : {}),
      code,
      ...(resolvedChallengeId ? {challenge_id: resolvedChallengeId} : {}),
    },
  );
  forgetSmsChallenge(scope, resolvedChallengeId);
  return response.data;
};

export const confirmPasswordChange = async (
  verificationToken: string,
  newPassword: string,
  confirmPassword: string,
): Promise<MessageResponse> => {
  const { encryptedPassword, keyId } = await encryptPasswordWithCurrentKey(newPassword);
  const { encryptedPassword: encryptedConfirm } = await encryptPasswordWithCurrentKey(confirmPassword);
  const response = await authApi.post<MessageResponse>('/authn/change-password/confirm/', {
    verification_token: verificationToken,
    new_password: encryptedPassword,
    new_password_confirm: encryptedConfirm,
    key_id: keyId,
  });
  return response.data;
};

export const requestAccountDeletionCode = async (): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/delete-account/request-code/', {});
  return response.data;
};

export const verifyAccountDeletionCode = async (code: string): Promise<VerificationTokenResponse> => {
  const response = await authApi.post<VerificationTokenResponse>('/authn/delete-account/verify-code/', { code });
  return response.data;
};

export const confirmAccountDeletion = async (verificationToken: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/delete-account/confirm/', {
    verification_token: verificationToken,
  });
  return response.data;
};

export const subscribe = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/subscribe/', { email });
  return response.data;
};
