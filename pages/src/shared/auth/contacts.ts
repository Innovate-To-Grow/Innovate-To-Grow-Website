import authApi from './client';
import type { ContactEmail, ContactPhone, MessageResponse } from './types';

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

export const getContactEmails = async (): Promise<ContactEmail[]> => {
  const response = await authApi.get<ContactEmail[]>('/authn/contact-emails/');
  return response.data;
};

export const createContactEmail = async (data: {
  email_address: string;
  email_type?: 'secondary' | 'other';
  subscribe?: boolean;
}): Promise<ContactEmail> => {
  const response = await authApi.post<ContactEmail>('/authn/contact-emails/', data);
  return response.data;
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
  const response = await authApi.post<MessageResponse>(`/authn/contact-emails/${id}/request-verification/`);
  return response.data;
};

export const verifyContactEmailCode = async (id: string, code: string): Promise<ContactEmail> => {
  const response = await authApi.post<ContactEmail>(`/authn/contact-emails/${id}/verify-code/`, { code });
  return response.data;
};
