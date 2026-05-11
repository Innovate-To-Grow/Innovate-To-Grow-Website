import axios from 'axios';

import { clearTokens, getAccessToken, getRefreshToken, getStoredUser, setTokens } from './storage';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const authApi = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

let refreshInFlight: Promise<string | null> | null = null;
const retriedRequests = new WeakSet<object>();

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(`${API_BASE_URL}/authn/refresh/`, {
        refresh: refreshToken,
      })
      .then((response) => {
        const { access, refresh: newRefresh } = response.data;
        const user = getStoredUser();
        if (user) {
          setTokens({ access, refresh: newRefresh ?? refreshToken }, user);
        }
        window.dispatchEvent(new Event('i2g-auth-state-change'));
        return access as string;
      })
      .catch(() => {
        clearTokens();
        window.dispatchEvent(new Event('i2g-auth-state-change'));
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }

  return refreshInFlight;
}

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

    if (error.response?.status === 401 && originalRequest && !retriedRequests.has(originalRequest)) {
      retriedRequests.add(originalRequest);

      const access = await refreshAccessToken();
      if (access) {
        originalRequest.headers.Authorization = `Bearer ${access}`;
        return authApi(originalRequest);
      }
    }

    return Promise.reject(error);
  }
);

export { authApi };
