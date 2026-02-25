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
  login as apiLogin,
  register as apiRegister,
  verifyEmail as apiVerifyEmail,
  getProfile as apiGetProfile,
  logout as apiLogout,
  getStoredUser,
  isAuthenticated as checkIsAuthenticated,
} from '../../services/auth';

// Custom event names for cross-root communication
const AUTH_STATE_CHANGE_EVENT = 'i2g-auth-state-change';
const AUTH_MODAL_EVENT = 'i2g-auth-modal';

// Dispatch auth state change to sync across React roots
const dispatchAuthStateChange = () => {
  window.dispatchEvent(new CustomEvent(AUTH_STATE_CHANGE_EVENT));
};

// Dispatch modal state change
const dispatchModalEvent = (view: AuthModalView) => {
  window.dispatchEvent(new CustomEvent(AUTH_MODAL_EVENT, { detail: { view } }));
};

// ======================== Types ========================

export type AuthModalView = 'login' | 'register' | 'verify-pending' | 'profile' | null;

interface AuthContextValue {
  // State
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Modal state
  modalView: AuthModalView;
  openModal: (view: AuthModalView) => void;
  closeModal: () => void;

  // Auth actions
  login: (email: string, password: string) => Promise<LoginResponse>;
  register: (email: string, password: string, passwordConfirm: string, firstName?: string, lastName?: string, organization?: string) => Promise<RegisterResponse>;
  verifyEmail: (token: string) => Promise<VerifyEmailResponse>;
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
  modalView: null,
  openModal: () => {},
  closeModal: () => {},
  login: async () => { throw new Error('Not implemented'); },
  register: async () => { throw new Error('Not implemented'); },
  verifyEmail: async () => { throw new Error('Not implemented'); },
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
  const [modalView, setModalView] = useState<AuthModalView>(null);
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

  // Listen for modal events from other React roots
  useEffect(() => {
    const handleModalEvent = (event: CustomEvent<{ view: AuthModalView }>) => {
      setModalView(event.detail.view);
      setError(null);
    };

    window.addEventListener(AUTH_MODAL_EVENT, handleModalEvent as EventListener);

    return () => {
      window.removeEventListener(AUTH_MODAL_EVENT, handleModalEvent as EventListener);
    };
  }, []);

  const openModal = useCallback((view: AuthModalView) => {
    setError(null);
    setModalView(view);
    dispatchModalEvent(view);
  }, []);

  const closeModal = useCallback(() => {
    setError(null);
    setModalView(null);
    dispatchModalEvent(null);
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
      closeModal();
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [closeModal]);

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
      setModalView('verify-pending');
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
      closeModal();
      return response;
    } catch (err: unknown) {
      const message = getErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [closeModal]);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    dispatchAuthStateChange();
    closeModal();
  }, [closeModal]);

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
    modalView,
    openModal,
    closeModal,
    login,
    register,
    verifyEmail,
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
      // Handle field-specific errors
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value)) {
          return value[0] as string;
        }
        if (typeof value === 'string') {
          return value;
        }
      }
    }
  }
  return 'An unexpected error occurred. Please try again.';
}

