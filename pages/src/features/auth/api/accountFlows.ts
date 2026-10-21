// Password reset, password change, and account deletion: the code-verified account flows.

import { encryptPasswordWithCurrentKey } from '@/lib/security';
import { withVerifiedSend } from '@/features/auth/verification';
import { authApi } from './client';
import type {
  MessageResponse,
  PasswordChangeRequestResponse,
  SmsChallengeResponse,
  VerificationTokenResponse,
} from './types';
import {
  forgetSmsChallenge,
  passwordChangeChallengeScope,
  passwordResetChallengeScope,
  readSmsChallenge,
  rememberSmsChallenge,
} from './smsChallenges';

export const requestPasswordReset = async (
  email: string,
): Promise<SmsChallengeResponse> => {
  const response = await withVerifiedSend({
    operation: 'password_reset.request_code',
    destinationKind: email.includes('@') ? 'email' : 'phone',
    destination: email,
    extraChallenge: {identifier: email},
    execute: async (verification) => {
      return (
        await authApi.post<SmsChallengeResponse>('/authn/password-reset/request-code/', {
          email,
          ...verification,
        })
      ).data;
    },
  });
  // The public endpoint deliberately has the same response shape for email,
  // phone, and unknown identifiers. Persist any opaque challenge returned; the
  // email verifier safely ignores it, while SMS verification requires it.
  rememberSmsChallenge(
    passwordResetChallengeScope(email),
    response.challenge_id,
  );
  return response;
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
  const response = await withVerifiedSend({
    operation: 'change_password.request_code',
    destinationKind: 'email',
    destination: email || 'account',
    extraChallenge: email ? {email} : undefined,
    execute: async (verification) => {
      return (
        await authApi.post<PasswordChangeRequestResponse>(
          '/authn/change-password/request-code/',
          email ? {email, ...verification} : {...verification},
        )
      ).data;
    },
  });
  rememberSmsChallenge(
    passwordChangeChallengeScope(email),
    response.channel === 'sms' ? response.challenge_id : undefined,
  );
  return response;
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
  return withVerifiedSend({
    operation: 'delete_account.request_code',
    destinationKind: 'email',
    destination: 'account',
    execute: async (verification) => {
      const response = await authApi.post<MessageResponse>('/authn/delete-account/request-code/', {
        ...verification,
      });
      return response.data;
    },
  });
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
