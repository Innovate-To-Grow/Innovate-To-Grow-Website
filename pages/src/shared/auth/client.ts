import axios from 'axios';

import { clearTokens, getAccessToken, getRefreshToken, getStoredUser, setTokens } from './storage';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const authApi = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

authApi.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (config.data instanceof FormData && config.headers) {
    delete config.headers['Content-Type'];
  }
  return config;
});

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

export default authApi;
