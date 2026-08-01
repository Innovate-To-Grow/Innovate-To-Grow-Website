import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  bootstrapAuthSession,
  getStoredSession,
  isAuthenticated as checkIsAuthenticated,
  type StoredAuthSession,
  type User,
} from '@/features/auth/api';
import {
  AUTH_STATE_CHANGE_EVENT,
  defaultContextValue,
  type AuthContextValue,
} from './context/shared';
import {useAuthActions} from './context/useAuthActions';

const AuthContext = createContext<AuthContextValue>(defaultContextValue);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider = ({children}: AuthProviderProps) => {
  const [user, setUser] = useState<User | null>(null);
  const [requiresProfileCompletion, setRequiresProfileCompletion] =
    useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initializationCompleteRef = useRef(false);

  const applySession = useCallback((session: StoredAuthSession | null) => {
    setUser(session?.user ?? null);
    setRequiresProfileCompletion(
      session?.requires_profile_completion ?? false,
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    void bootstrapAuthSession().then((session) => {
      if (cancelled) return;
      applySession(session);
      initializationCompleteRef.current = true;
      setIsInitializing(false);
    });
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  // Keep the separate application/menu React roots and other browser tabs on
  // the same persisted generation.
  useEffect(() => {
    let syncSequence = 0;
    const handleAuthStateChange = () => {
      const sequence = ++syncSequence;
      const stored = getStoredSession();
      if (!stored) {
        applySession(null);
        if (initializationCompleteRef.current) setIsInitializing(false);
        return;
      }
      if (checkIsAuthenticated()) {
        applySession(stored);
        if (initializationCompleteRef.current) setIsInitializing(false);
        return;
      }
      void bootstrapAuthSession().then((session) => {
        if (sequence === syncSequence) applySession(session);
      });
    };

    window.addEventListener(
      AUTH_STATE_CHANGE_EVENT,
      handleAuthStateChange,
    );
    window.addEventListener('storage', handleAuthStateChange);
    return () => {
      syncSequence += 1;
      window.removeEventListener(
        AUTH_STATE_CHANGE_EVENT,
        handleAuthStateChange,
      );
      window.removeEventListener('storage', handleAuthStateChange);
    };
  }, [applySession]);

  const {
    clearError,
    login,
    register,
    requestEmailAuthCode,
    verifyEmailAuthCode,
    requestPhoneAuthCode,
    verifyPhoneAuthCode,
    requestLoginCode,
    verifyLoginCode,
    verifyRegistrationCode,
    resendRegistrationCode,
    requestPasswordReset,
    verifyPasswordResetCode,
    confirmPasswordReset,
    requestPasswordChangeCode,
    verifyPasswordChangeCode,
    confirmPasswordChange,
    logout,
    refreshProfile,
    clearProfileCompletionRequirement,
  } = useAuthActions({
    setUser,
    setRequiresProfileCompletion,
    setError,
    setIsLoading,
  });

  const value: AuthContextValue = useMemo(
    () => ({
      user,
      isAuthenticated: !!user,
      isInitializing,
      requiresProfileCompletion,
      isLoading,
      error,
      login,
      register,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
      requestLoginCode,
      verifyLoginCode,
      verifyRegistrationCode,
      resendRegistrationCode,
      requestPasswordReset,
      verifyPasswordResetCode,
      confirmPasswordReset,
      requestPasswordChangeCode,
      verifyPasswordChangeCode,
      confirmPasswordChange,
      logout,
      refreshProfile,
      clearProfileCompletionRequirement,
      clearError,
    }),
    [
      user,
      isInitializing,
      requiresProfileCompletion,
      isLoading,
      error,
      login,
      register,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
      requestLoginCode,
      verifyLoginCode,
      verifyRegistrationCode,
      resendRegistrationCode,
      requestPasswordReset,
      verifyPasswordResetCode,
      confirmPasswordReset,
      requestPasswordChangeCode,
      verifyPasswordChangeCode,
      confirmPasswordChange,
      logout,
      refreshProfile,
      clearProfileCompletionRequirement,
      clearError,
    ],
  );

  return (
    <AuthContext.Provider value={value}>
      {isInitializing ? null : children}
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);
