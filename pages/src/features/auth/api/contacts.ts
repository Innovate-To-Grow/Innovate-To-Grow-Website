import { withVerifiedSend } from '@/features/auth/verification';
import { authApi } from './client';
import type {
  ContactEmail,
  ContactPhone,
  MessageResponse,
  SmsChallengeResponse,
} from './types';
import {
  contactPhoneChallengeScope,
  forgetSmsChallenge,
  readSmsChallenge,
  rememberSmsChallenge,
} from './smsChallenges';

export const getContactPhones = async (): Promise<ContactPhone[]> => {
  const response = await authApi.get<ContactPhone[]>('/authn/contact-phones/');
  return response.data;
};

export const createContactPhone = async (data: {
  phone_number: string;
  region: string;
  subscribe?: boolean;
}): Promise<ContactPhone> => {
  const response = await authApi.post<ContactPhone>('/authn/contact-phones/', data);
  return response.data;
};

export const updateContactPhone = async (
  id: string,
  data: { subscribe: boolean },
): Promise<ContactPhone> => {
  const response = await authApi.patch<ContactPhone>(`/authn/contact-phones/${id}/`, data);
  return response.data;
};

export const deleteContactPhone = async (id: string): Promise<void> => {
  await authApi.delete(`/authn/contact-phones/${id}/`);
};

export const requestContactPhoneVerification = async (id: string): Promise<SmsChallengeResponse> => {
  const response = await withVerifiedSend({
    operation: 'contact_phone.request_verification',
    destinationKind: 'phone',
    destination: id,
    extraChallenge: {contact_id: id},
    execute: async (verification) => {
      return (
        await authApi.post<SmsChallengeResponse>(
          `/authn/contact-phones/${id}/request-verification/`,
          verification,
        )
      ).data;
    },
  });
  rememberSmsChallenge(
    contactPhoneChallengeScope(id),
    response.challenge_id,
  );
  return response;
};

export const verifyContactPhoneCode = async (
  id: string,
  code: string,
  challengeId?: string,
): Promise<ContactPhone> => {
  const scope = contactPhoneChallengeScope(id);
  const resolvedChallengeId = challengeId ?? readSmsChallenge(scope);
  const response = await authApi.post<ContactPhone>(
    `/authn/contact-phones/${id}/verify-code/`,
    {
      code,
      ...(resolvedChallengeId ? {challenge_id: resolvedChallengeId} : {}),
    },
  );
  forgetSmsChallenge(scope, resolvedChallengeId);
  return response.data;
};

export const getContactEmails = async (): Promise<ContactEmail[]> => {
  const response = await authApi.get<ContactEmail[]>('/authn/contact-emails/');
  return response.data;
};

export const createContactEmail = async (data: {
  email_address: string;
  email_type?: 'secondary' | 'other';
  subscribe?: boolean;
}): Promise<ContactEmail> => {
  return withVerifiedSend({
    operation: 'contact_email.create',
    destinationKind: 'email',
    destination: data.email_address,
    extraChallenge: {email_address: data.email_address},
    execute: async (verification) => {
      const response = await authApi.post<ContactEmail>('/authn/contact-emails/', {
        ...data,
        ...verification,
      });
      return response.data;
    },
  });
};

export const updateContactEmail = async (
  id: string,
  data: { email_type?: 'secondary' | 'other'; subscribe?: boolean },
): Promise<ContactEmail> => {
  const response = await authApi.patch<ContactEmail>(`/authn/contact-emails/${id}/`, data);
  return response.data;
};

export const deleteContactEmail = async (id: string): Promise<void> => {
  await authApi.delete(`/authn/contact-emails/${id}/`);
};

export const requestContactEmailVerification = async (id: string): Promise<MessageResponse> => {
  return withVerifiedSend({
    operation: 'contact_email.request_verification',
    destinationKind: 'email',
    destination: id,
    extraChallenge: {contact_id: id},
    execute: async (verification) => {
      const response = await authApi.post<MessageResponse>(
        `/authn/contact-emails/${id}/request-verification/`,
        verification,
      );
      return response.data;
    },
  });
};

export const verifyContactEmailCode = async (id: string, code: string): Promise<ContactEmail> => {
  const response = await authApi.post<ContactEmail>(`/authn/contact-emails/${id}/verify-code/`, { code });
  return response.data;
};

export const makeContactEmailPrimary = async (id: string): Promise<ContactEmail> => {
  const response = await authApi.post<ContactEmail>(`/authn/contact-emails/${id}/make-primary/`);
  return response.data;
};
