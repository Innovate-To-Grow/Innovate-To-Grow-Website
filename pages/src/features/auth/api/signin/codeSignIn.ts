import { withVerifiedSend } from '@/features/auth/verification';
import { authApi } from '../session/client';
import {persistAuthSession} from '../session/storage';
import type {
  EmailAuthRequestResponse,
  EmailAuthSource,
  EmailAuthVerifyResponse,
  LoginResponse,
  MessageResponse,
  PhoneAuthRequestResponse,
  PhoneAuthSource,
} from '../contracts/types';
import {
  forgetSmsChallenge,
  phoneAuthChallengeScope,
  readSmsChallenge,
  rememberSmsChallenge,
} from '../session/smsChallenges';

export const requestLoginCode = async (email: string): Promise<MessageResponse> => {
  return withVerifiedSend({
    operation: 'login.request_code',
    destinationKind: 'email',
    destination: email,
    execute: async (verification) => {
      const response = await authApi.post<MessageResponse>('/authn/login/request-code/', {
        email,
        ...verification,
      });
      return response.data;
    },
  });
};

export const requestEmailAuthCode = async (
  email: string,
  source: EmailAuthSource = 'login',
  event?: string,
): Promise<EmailAuthRequestResponse> => {
  return withVerifiedSend({
    operation: 'email_auth.request_code',
    destinationKind: 'email',
    destination: email,
    extraChallenge: event ? {event} : undefined,
    execute: async (verification) => {
      const response = await authApi.post<EmailAuthRequestResponse>('/authn/email-auth/request-code/', {
        email,
        source,
        ...(event ? {event} : {}),
        ...verification,
      });
      return response.data;
    },
  });
};

export const verifyLoginCode = async (email: string, code: string): Promise<LoginResponse> => {
  // The emailed code is the credential, so the stored session must not ride
  // along (see `skipAuth` in client.ts): a stale one would otherwise be
  // refreshed, and destroyed, on behalf of a request that never needed it.
  const response = await authApi.post<LoginResponse>(
    '/authn/login/verify-code/',
    { email, code },
    { skipAuth: true },
  );
  persistAuthSession(response.data);
  return response.data;
};

export const verifyEmailAuthCode = async (email: string, code: string): Promise<EmailAuthVerifyResponse> => {
  // The emailed link exchanges its one-time code here; the stored session must
  // not ride along (see `skipAuth` in client.ts).
  const response = await authApi.post<EmailAuthVerifyResponse>(
    '/authn/email-auth/verify-code/',
    { email, code },
    { skipAuth: true },
  );
  persistAuthSession(response.data);
  return response.data;
};

export const requestPhoneAuthCode = async (
  phoneNumber: string,
  region: string = '1-US',
  source: PhoneAuthSource = 'login',
): Promise<PhoneAuthRequestResponse> => {
  const response = await withVerifiedSend({
    operation: 'phone_auth.request_code',
    destinationKind: 'phone',
    destination: phoneNumber,
    extraChallenge: {region, phone_number: phoneNumber},
    execute: async (verification) => {
      return (
        await authApi.post<PhoneAuthRequestResponse>('/authn/phone-auth/request-code/', {
          phone_number: phoneNumber,
          region,
          source,
          ...verification,
        })
      ).data;
    },
  });
  rememberSmsChallenge(
    phoneAuthChallengeScope(phoneNumber, region),
    response.challenge_id,
  );
  return response;
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
