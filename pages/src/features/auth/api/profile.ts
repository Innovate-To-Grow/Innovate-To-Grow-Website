import { authApi } from './client';
import {getStoredSession, updateStoredUser} from './storage';
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
  const session = getStoredSession();
  const response = await authApi.patch<ProfileResponse>('/authn/profile/', data);
  // The header's account button shows the member's name; keep the stored copy current and tell
  // the other React roots (the menu) to re-read it.
  if (
    session &&
    updateStoredUser(
      (user) => ({...user, first_name: response.data.first_name, last_name: response.data.last_name}),
      session.generation,
    )
  ) {
    window.dispatchEvent(new Event('i2g-auth-state-change'));
  }
  return response.data;
};

export const uploadProfileImage = async (file: File): Promise<ProfileResponse> => {
  const session = getStoredSession();
  const formData = new FormData();
  formData.append('profile_image', file);
  const response = await authApi.patch<ProfileResponse>('/authn/profile/', formData);
  if (session) {
    updateStoredUser(
      (user) => ({
        ...user,
        profile_image: response.data.profile_image,
      }),
      session.generation,
    );
  }
  return response.data;
};

export const getAccountEmails = async (): Promise<AccountEmailsResponse> => {
  const response = await authApi.get<AccountEmailsResponse>('/authn/account-emails/');
  return response.data;
};
