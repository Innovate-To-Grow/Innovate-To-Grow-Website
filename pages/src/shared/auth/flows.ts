import axios from 'axios';

import { clearKeyCache, encryptPasswordWithCurrentKey } from '../../services/crypto';
import authApi from './client';
import {
  clearProfileCompletionRequired,
  setProfileCompletionRequired,
  setTokens,
} from './storage';
import type {
  EmailAuthRequestResponse,
  EmailAuthVerifyResponse,
  LoginResponse,
  MessageResponse,
  RegisterResponse,
  VerificationTokenResponse,
} from './types';

export const register = async (
  email: string,
  password: string,
  passwordConfirm: string,
  firstName?: string,
  lastName?: string,
  organization?: string,
): Promise<RegisterResponse> => {
  try {
    const { encryptedPassword, keyId } = await encryptPasswordWithCurrentKey(password);
    const { encryptedPassword: encryptedConfirm } = await encryptPasswordWithCurrentKey(passwordConfirm);
    const response = await authApi.post<RegisterResponse>('/authn/register/', {
      email,
      password: encryptedPassword,
      password_confirm: encryptedConfirm,
      key_id: keyId,
      ...(firstName && { first_name: firstName }),
      ...(lastName && { last_name: lastName }),
      ...(organization && { organization }),
    });
    clearProfileCompletionRequired();
    return response.data;
  } catch (error) {
    if (error instanceof Error && error.message.includes('decrypt')) {
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
    const { access, refresh, user } = response.data;
    setTokens({ access, refresh }, user);
    clearProfileCompletionRequired();
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data?.password?.includes('decrypt')) {
      clearKeyCache();
    }
    throw error;
  }
};

export const requestLoginCode = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/login/request-code/', { email });
  return response.data;
};

export const requestEmailAuthCode = async (email: string): Promise<EmailAuthRequestResponse> => {
  const response = await authApi.post<EmailAuthRequestResponse>('/authn/email-auth/request-code/', { email });
  return response.data;
};

export const verifyLoginCode = async (email: string, code: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/login/verify-code/', { email, code });
  const { access, refresh, user } = response.data;
  setTokens({ access, refresh }, user);
  clearProfileCompletionRequired();
  return response.data;
};

export const verifyEmailAuthCode = async (email: string, code: string): Promise<EmailAuthVerifyResponse> => {
  const response = await authApi.post<EmailAuthVerifyResponse>('/authn/email-auth/verify-code/', { email, code });
  const { access, refresh, user, requires_profile_completion: requiresProfileCompletion } = response.data;
  setTokens({ access, refresh }, user);
  setProfileCompletionRequired(requiresProfileCompletion);
  return response.data;
};

export const verifyRegistrationCode = async (email: string, code: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/register/verify-code/', { email, code });
  const { access, refresh, user } = response.data;
  setTokens({ access, refresh }, user);
  clearProfileCompletionRequired();
  return response.data;
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

export const subscribe = async (email: string): Promise<MessageResponse> => {
  const response = await authApi.post<MessageResponse>('/authn/subscribe/', { email });
  return response.data;
};
