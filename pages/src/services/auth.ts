import axios from 'axios';
import { encryptPasswordWithCurrentKey, clearKeyCache } from './crypto';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// ======================== Types ========================

export interface User {
  member_uuid: string;
  email: string;
  username: string;
  display_name?: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginResponse {
  message: string;
  access: string;
  refresh: string;
  user: User;
}

export interface EmailAuthRequestResponse {
  message: string;
  flow: 'login' | 'register';
  next_step: 'verify_code';
}

export interface EmailAuthVerifyResponse extends LoginResponse {
  next_step: 'account' | 'complete_profile';
  requires_profile_completion: boolean;
}

export interface RegisterResponse {
  message: string;
  next_step: string;
}

export interface MessageResponse {
  message: string;
}

export interface VerificationTokenResponse {
  message: string;
  verification_token: string;
}

export interface AccountEmailsResponse {
  emails: string[];
}

export interface ProfileResponse {
  member_uuid: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  display_name: string;
  organization: string;
  email_subscribe: boolean;
  is_active: boolean;
  date_joined: string;
  profile_image?: string;
}

export interface ContactEmail {
  id: string;
  email_address: string;
  email_type: 'primary' | 'secondary' | 'other';
  subscribe: boolean;
  verified: boolean;
  created_at: string;
}

// ======================== Token Storage ========================

const ACCESS_TOKEN_KEY = 'i2g_access_token';
const REFRESH_TOKEN_KEY = 'i2g_refresh_token';
const USER_KEY = 'i2g_user';
const PROFILE_COMPLETION_REQUIRED_KEY = 'i2g_profile_completion_required';

export const isProfileCompletionRequired = (): boolean => {
  return sessionStorage.getItem(PROFILE_COMPLETION_REQUIRED_KEY) === 'true';
};

export const setProfileCompletionRequired = (required: boolean): void => {
  if (required) {
    sessionStorage.setItem(PROFILE_COMPLETION_REQUIRED_KEY, 'true');
    return;
  }
  sessionStorage.removeItem(PROFILE_COMPLETION_REQUIRED_KEY);
};

export const clearProfileCompletionRequired = (): void => {
  sessionStorage.removeItem(PROFILE_COMPLETION_REQUIRED_KEY);
};

export const getAccessToken = (): string | null => {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
};

export const getRefreshToken = (): string | null => {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
};

export const getStoredUser = (): User | null => {
  const userStr = localStorage.getItem(USER_KEY);
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
};

export const setTokens = (tokens: AuthTokens, user: User): void => {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};

export const clearTokens = (): void => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  clearProfileCompletionRequired();
};

// ======================== Axios Instance ========================

const authApi = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth header to requests
authApi.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // When sending FormData, remove Content-Type so axios sets multipart boundary
  if (config.data instanceof FormData && config.headers) {
    delete config.headers['Content-Type'];
  }
  return config;
});

// Handle token refresh on 401
authApi.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const refreshToken = getRefreshToken();
      if (refreshToken) {
        try {
          const response = await axios.post(`${API_BASE_URL}/authn/refresh/`, {
            refresh: refreshToken,
          });

          const { access, refresh: newRefresh } = response.data;
          const user = getStoredUser();
          if (user) {
            setTokens({ access, refresh: newRefresh ?? refreshToken }, user);
          }

          // Notify other React roots that auth state has refreshed
          window.dispatchEvent(new Event('i2g-auth-state-change'));

          originalRequest.headers.Authorization = `Bearer ${access}`;
          return authApi(originalRequest);
        } catch {
          clearTokens();
          window.dispatchEvent(new Event('i2g-auth-state-change'));
        }
      }
    }

    return Promise.reject(error);
  }
);

// ======================== Auth API Functions ========================

export const register = async (
  email: string,
  password: string,
  passwordConfirm: string,
  firstName?: string,
  lastName?: string,
  organization?: string,
): Promise<RegisterResponse> => {
  try {
    // Encrypt passwords with RSA public key
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
    // Clear key cache on encryption errors (might be stale key)
    if (error instanceof Error && error.message.includes('decrypt')) {
      clearKeyCache();
    }
    throw error;
  }
};

export const login = async (email: string, password: string): Promise<LoginResponse> => {
  try {
    // Encrypt password with RSA public key
    const { encryptedPassword, keyId } = await encryptPasswordWithCurrentKey(password);

    const response = await authApi.post<LoginResponse>('/authn/login/', {
      email,
      password: encryptedPassword,
      key_id: keyId,
    });

    // Store tokens and user
    const { access, refresh, user } = response.data;
    setTokens({ access, refresh }, user);
    clearProfileCompletionRequired();

    return response.data;
  } catch (error) {
    // Clear key cache on decryption errors from server (might be stale key)
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

export const getProfile = async (): Promise<ProfileResponse> => {
  const response = await authApi.get<ProfileResponse>('/authn/profile/');
  return response.data;
};

export const updateProfile = async (displayName: string): Promise<ProfileResponse> => {
  const response = await authApi.patch<ProfileResponse>('/authn/profile/', {
    display_name: displayName,
  });

  // Update stored user
  const user = getStoredUser();
  if (user) {
    user.display_name = displayName;
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  return response.data;
};

export const updateProfileFields = async (data: {
  first_name?: string;
  last_name?: string;
  display_name?: string;
  organization?: string;
  email_subscribe?: boolean;
}): Promise<ProfileResponse> => {
  const response = await authApi.patch<ProfileResponse>('/authn/profile/', data);

  // Update stored user display_name if changed
  if (data.display_name !== undefined) {
    const user = getStoredUser();
    if (user) {
      user.display_name = data.display_name;
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
  }

  return response.data;
};

export const uploadProfileImage = async (file: File): Promise<ProfileResponse> => {
  const formData = new FormData();
  formData.append('profile_image', file);

  const response = await authApi.patch<ProfileResponse>('/authn/profile/', formData);

  return response.data;
};

export const changePassword = async (
  currentPassword: string,
  newPassword: string,
  confirmPassword: string,
): Promise<{ message: string }> => {
  const { encryptedPassword: encCurrent, keyId } = await encryptPasswordWithCurrentKey(currentPassword);
  const { encryptedPassword: encNew } = await encryptPasswordWithCurrentKey(newPassword);
  const { encryptedPassword: encConfirm } = await encryptPasswordWithCurrentKey(confirmPassword);

  const response = await authApi.post<{ message: string }>('/authn/change-password/', {
    current_password: encCurrent,
    new_password: encNew,
    new_password_confirm: encConfirm,
    key_id: keyId,
  });
  return response.data;
};

export const getAccountEmails = async (): Promise<AccountEmailsResponse> => {
  const response = await authApi.get<AccountEmailsResponse>('/authn/account-emails/');
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

// ======================== Contact Emails ========================

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

// ======================== Session ========================

export const logout = (): void => {
  clearTokens();
};

export const isAuthenticated = (): boolean => {
  const token = getAccessToken();
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' && payload.exp > Date.now() / 1000;
  } catch {
    return false;
  }
};

export default authApi;
