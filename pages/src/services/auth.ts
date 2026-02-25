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

export interface RegisterResponse {
  message: string;
  email: string;
  verification_token?: string; // Only in dev mode
}

export interface VerifyEmailResponse {
  message: string;
  access: string;
  refresh: string;
  user: User;
}

export interface ProfileResponse {
  member_uuid: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  display_name: string;
  organization: string;
  is_active: boolean;
  date_joined: string;
}

// ======================== Token Storage ========================

const ACCESS_TOKEN_KEY = 'i2g_access_token';
const REFRESH_TOKEN_KEY = 'i2g_refresh_token';
const USER_KEY = 'i2g_user';

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

          const { access } = response.data;
          const user = getStoredUser();
          if (user) {
            setTokens({ access, refresh: refreshToken }, user);
          }

          originalRequest.headers.Authorization = `Bearer ${access}`;
          return authApi(originalRequest);
        } catch {
          clearTokens();
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

    return response.data;
  } catch (error) {
    // Clear key cache on decryption errors from server (might be stale key)
    if (axios.isAxiosError(error) && error.response?.data?.password?.includes('decrypt')) {
      clearKeyCache();
    }
    throw error;
  }
};

export const verifyEmail = async (token: string): Promise<VerifyEmailResponse> => {
  const response = await authApi.post<VerifyEmailResponse>('/authn/verify-email/', {
    token,
  });

  // Store tokens and user
  const { access, refresh, user } = response.data;
  setTokens({ access, refresh }, user);

  return response.data;
};

export const resendVerification = async (email: string): Promise<{ message: string }> => {
  const response = await authApi.post<{ message: string }>('/authn/resend-verification/', {
    email,
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

export const logout = (): void => {
  clearTokens();
};

export const isAuthenticated = (): boolean => {
  return !!getAccessToken();
};

export default authApi;

