import axios from 'axios';

import { clearKeyCache, encryptPasswordWithCurrentKey } from '../crypto';
import { authApi } from './client';
import {
  clearProfileCompletionRequired,
  persistAuthSession,
} from './storage';
import type {
  EmailAuthFlow,
  EmailAuthRequestResponse,
  EmailAuthSource,
  EmailAuthVerifyResponse,
  LoginResponse,
  MessageResponse,
  RegisterResponse,
  VerificationTokenResponse,
} from './types';

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
    clearProfileCompletionRequired();
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
): Promise<EmailAuthRequestResponse> => {
  const response = await authApi.post<EmailAuthRequestResponse>('/authn/email-auth/request-code/', { email, source });
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

export const requestPasswordReset = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/password-reset/request-code/', { email });
  return response.data;
};

export const verifyPasswordResetCode = async (email: string, code: string): Promise<VerificationTokenResponse> => {
  const response = await authApi.post<VerificationTokenResponse>('/authn/password-reset/verify-code/', { email, code });
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

export const requestPasswordChangeCode = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/change-password/request-code/', { email });
  return response.data;
};

export const verifyPasswordChangeCode = async (
  email: string,
  code: string,
): Promise<VerificationTokenResponse> => {
  const response = await authApi.post<VerificationTokenResponse>('/authn/change-password/verify-code/', { email, code });
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
