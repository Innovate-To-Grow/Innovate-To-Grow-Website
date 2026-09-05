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
  type StoredAuthSession,
  type User,
} from '@/features/auth/api';
import {VerifiedSendStatus} from '@/features/auth/verification';
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
  const [initialSession] = useState<StoredAuthSession | null>(() => getStoredSession());
  const [user, setUser] = useState<User | null>(initialSession?.user ?? null);
  const [requiresProfileCompletion, setRequiresProfileCompletion] =
    useState(initialSession?.requires_profile_completion ?? false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [unverified, setUnverified] = useState(Boolean(initialSession));
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
    void bootstrapAuthSession().then((result) => {
      if (cancelled) return;
      applySession(result.session);
      setUnverified(result.status === 'unverified');
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
        setUnverified(false);
        if (initializationCompleteRef.current) setIsInitializing(false);
        return;
      }
      setUnverified(true);
      void bootstrapAuthSession().then((result) => {
        if (sequence === syncSequence) {
          applySession(result.session);
          setUnverified(result.status === 'unverified');
        }
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
      // Persisted identity may render optimistically, but protected decisions stay
      // anonymous until the session endpoint has verified this generation.
      isAuthenticated: !!user && !unverified,
      isInitializing,
      unverified,
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
      unverified,
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
      {children}
      <VerifiedSendStatus />
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);
