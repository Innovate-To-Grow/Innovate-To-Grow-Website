import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import {
  type User,
  type LoginResponse,
  type RegisterResponse,
  type VerifyEmailResponse,
  type RequestCodeResponse,
  type VerifyCodeResponse,
  login as apiLogin,
  register as apiRegister,
  verifyEmail as apiVerifyEmail,
  requestLoginCode as apiRequestLoginCode,
  verifyLoginCode as apiVerifyLoginCode,
  verifyEmailCode as apiVerifyEmailCode,
  getProfile as apiGetProfile,
  logout as apiLogout,
  getStoredUser,
  isAuthenticated as checkIsAuthenticated,
} from '../../services/auth';

// Custom event names for cross-root communication
const AUTH_STATE_CHANGE_EVENT = 'i2g-auth-state-change';

// Dispatch auth state change to sync across React roots
const dispatchAuthStateChange = () => {
  window.dispatchEvent(new CustomEvent(AUTH_STATE_CHANGE_EVENT));
};

// ======================== Types ========================

interface AuthContextValue {
  // State
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Auth actions
  login: (email: string, password: string) => Promise<LoginResponse>;
  requestLoginCode: (email: string) => Promise<RequestCodeResponse>;
  verifyLoginCode: (email: string, code: string) => Promise<VerifyCodeResponse>;
  register: (email: string, password: string, passwordConfirm: string, firstName?: string, lastName?: string, organization?: string) => Promise<RegisterResponse>;
  verifyEmail: (token: string) => Promise<VerifyEmailResponse>;
  verifyEmailCode: (email: string, code: string) => Promise<VerifyCodeResponse>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
  clearError: () => void;

  // Pending verification email
  pendingEmail: string | null;
  setPendingEmail: (email: string | null) => void;
}

const defaultContextValue: AuthContextValue = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  login: async () => { throw new Error('Not implemented'); },
  requestLoginCode: async () => { throw new Error('Not implemented'); },
  verifyLoginCode: async () => { throw new Error('Not implemented'); },
  register: async () => { throw new Error('Not implemented'); },
  verifyEmail: async () => { throw new Error('Not implemented'); },
  verifyEmailCode: async () => { throw new Error('Not implemented'); },
  logout: () => {},
  refreshProfile: async () => {},
  clearError: () => {},
  pendingEmail: null,
  setPendingEmail: () => {},
};

const AuthContext = createContext<AuthContextValue>(defaultContextValue);

// ======================== Provider ========================

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);

  // Initialize auth state from localStorage
  useEffect(() => {
    const storedUser = getStoredUser();
    if (storedUser && checkIsAuthenticated()) {
      setUser(storedUser);
    }
    setIsLoading(false);
  }, []);

  // Listen for auth state changes from other React roots
  useEffect(() => {
    const handleAuthStateChange = () => {
      const storedUser = getStoredUser();
      if (storedUser && checkIsAuthenticated()) {
        setUser(storedUser);
      } else {
        setUser(null);
      }
    };

    // Listen for custom auth state change events
    window.addEventListener(AUTH_STATE_CHANGE_EVENT, handleAuthStateChange);
    
    // Also listen for storage events (for cross-tab sync)
    window.addEventListener('storage', handleAuthStateChange);

    return () => {
      window.removeEventListener(AUTH_STATE_CHANGE_EVENT, handleAuthStateChange);
      window.removeEventListener('storage', handleAuthStateChange);
    };
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<LoginResponse> => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await apiLogin(email, password);
      setUser(response.user);
      dispatchAuthStateChange();
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (
    email: string,
    password: string,
    passwordConfirm: string,
    firstName?: string,
    lastName?: string,
    organization?: string,
  ): Promise<RegisterResponse> => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await apiRegister(email, password, passwordConfirm, firstName, lastName, organization);
      setPendingEmail(email);
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const requestLoginCode = useCallback(async (email: string): Promise<RequestCodeResponse> => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await apiRequestLoginCode(email);
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const verifyLoginCode = useCallback(async (email: string, code: string): Promise<VerifyCodeResponse> => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await apiVerifyLoginCode(email, code);
      setUser(response.user);
      dispatchAuthStateChange();
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const verifyEmail = useCallback(async (token: string): Promise<VerifyEmailResponse> => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await apiVerifyEmail(token);
      setUser(response.user);
      setPendingEmail(null);
      dispatchAuthStateChange();
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const verifyEmailCode = useCallback(async (email: string, code: string): Promise<VerifyCodeResponse> => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await apiVerifyEmailCode(email, code);
      setUser(response.user);
      setPendingEmail(null);
      dispatchAuthStateChange();
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    dispatchAuthStateChange();
  }, []);

  const refreshProfile = useCallback(async () => {
    if (!checkIsAuthenticated()) return;
    try {
      const profile = await apiGetProfile();
      setUser(prev => prev ? {
        ...prev,
        display_name: profile.display_name,
      } : null);
    } catch {
      // Silently fail - user might be logged out
    }
  }, []);

  const value: AuthContextValue = {
    user,
    isAuthenticated: !!user,
    isLoading,
    error,
    login,
    requestLoginCode,
    verifyLoginCode,
    register,
    verifyEmail,
    verifyEmailCode,
    logout,
    refreshProfile,
    clearError,
    pendingEmail,
    setPendingEmail,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// ======================== Hook ========================

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);

// ======================== Helpers ========================

function getErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as { response?: { data?: Record<string, unknown> } };
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      const messages: string[] = [];
      for (const value of Object.values(data)) {
        if (Array.isArray(value)) {
          for (const item of value) {
            if (typeof item === 'string') messages.push(item);
          }
        } else if (typeof value === 'string') {
          messages.push(value);
        }
      }
      if (messages.length > 0) return messages.join(' ');
    }
  }
  return 'An unexpected error occurred. Please try again.';
}
