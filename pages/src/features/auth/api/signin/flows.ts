import axios from 'axios';

import { clearKeyCache, encryptPasswordWithCurrentKey } from '@/lib/security';
import { withVerifiedSend } from '@/features/auth/verification';
import { authApi } from '../session/client';
import {persistAuthSession} from '../session/storage';
import type {LoginResponse, MessageResponse, RegisterResponse} from '../contracts/types';

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
    return await withVerifiedSend({
      operation: 'register',
      destinationKind: 'email',
      destination: email,
      execute: async (verification) => {
        const response = await authApi.post<RegisterResponse>('/authn/register/', {
          email,
          password: encryptedPassword,
          password_confirm: encryptedConfirm,
          key_id: keyId,
          first_name: firstName,
          last_name: lastName,
          organization,
          title,
          ...verification,
        });
        return response.data;
      },
    });
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

export const verifyRegistrationCode = async (email: string, code: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/register/verify-code/', { email, code });
  persistAuthSession(response.data);
  return response.data;
};

export const resendRegistrationCode = async (email: string): Promise<MessageResponse> => {
  return withVerifiedSend({
    operation: 'register.resend_code',
    destinationKind: 'email',
    destination: email,
    execute: async (verification) => {
      const response = await authApi.post<MessageResponse>('/authn/register/resend-code/', {
        email,
        ...verification,
      });
      return response.data;
    },
  });
};

// Re-exported so callers (and test mocks) keep one module for every auth flow.
export {
  requestLoginCode,
  requestEmailAuthCode,
  verifyLoginCode,
  verifyEmailAuthCode,
  requestPhoneAuthCode,
  verifyPhoneAuthCode,
} from './codeSignIn';
export {
  requestPasswordReset,
  verifyPasswordResetCode,
  confirmPasswordReset,
  requestPasswordChangeCode,
  verifyPasswordChangeCode,
  confirmPasswordChange,
  requestAccountDeletionCode,
  verifyAccountDeletionCode,
  confirmAccountDeletion,
} from '../account/accountFlows';
