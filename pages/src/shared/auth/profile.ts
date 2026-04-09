import authApi from './client';
import { updateStoredUser } from './storage';
import type { AccountEmailsResponse, ProfileResponse } from './types';

export const getProfile = async (): Promise<ProfileResponse> => {
  const response = await authApi.get<ProfileResponse>('/authn/profile/');
  return response.data;
};

export const updateProfileFields = async (data: {
  first_name?: string;
  middle_name?: string;
  last_name?: string;
  organization?: string;
  title?: string;
  email_subscribe?: boolean;
}): Promise<ProfileResponse> => {
  const response = await authApi.patch<ProfileResponse>('/authn/profile/', data);
  return response.data;
};

export const uploadProfileImage = async (file: File): Promise<ProfileResponse> => {
  const formData = new FormData();
  formData.append('profile_image', file);
  const response = await authApi.patch<ProfileResponse>('/authn/profile/', formData);
  updateStoredUser((user) => ({
    ...user,
    profile_image: response.data.profile_image,
  }));
  return response.data;
};

export const getAccountEmails = async (): Promise<AccountEmailsResponse> => {
  const response = await authApi.get<AccountEmailsResponse>('/authn/account-emails/');
  return response.data;
};
