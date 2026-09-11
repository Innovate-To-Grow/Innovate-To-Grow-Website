import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  bootstrapAuthSession,
  getStoredSession,
  type StoredAuthSession,
  type User,
} from '@/features/auth/api';
import {AUTH_SESSION_KEY} from '@/features/auth/api/storage';
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

  const applySession = useCallback((session: StoredAuthSession | null) => {
    setUser(session?.user ?? null);
    setRequiresProfileCompletion(
      session?.requires_profile_completion ?? false,
    );
  }, []);

  // Keep the separate application/menu React roots and other browser tabs on
  // the same persisted generation. Revalidating a known identity is not a
  // logout; a replacement generation must earn its own verification.
  useEffect(() => {
    let active = true;
    let syncSequence = 0;
    let verifiedSession: StoredAuthSession | null = null;
    const matchesVerifiedIdentity = (session: StoredAuthSession) =>
      verifiedSession?.generation === session.generation &&
      verifiedSession.user.member_uuid === session.user.member_uuid;

    const synchronize = async () => {
      const sequence = ++syncSequence;
      const stored = getStoredSession();
      if (!stored) {
        verifiedSession = null;
        applySession(null);
        setUnverified(false);
        setIsInitializing(false);
        return;
      }
      const alreadyVerified = matchesVerifiedIdentity(stored);
      if (!alreadyVerified) {
        verifiedSession = null;
        applySession(stored);
      }
      setUnverified(!alreadyVerified);
      setIsInitializing(!alreadyVerified);

      const result = await bootstrapAuthSession();
      if (!active || sequence !== syncSequence) return;
      const current = getStoredSession();
      if (
        current &&
        (current.generation !== stored.generation ||
          current.user.member_uuid !== stored.user.member_uuid)
      ) {
        // Storage can change before its event is delivered. Never apply the
        // previous account's completion to the replacement identity.
        void synchronize();
        return;
      }
      if (!current || result.status === 'anonymous') {
        verifiedSession = null;
        applySession(null);
        setUnverified(false);
      } else {
        if (
          result.status === 'verified' &&
          result.session.generation === current.generation &&
          result.session.user.member_uuid === current.user.member_uuid
        ) {
          verifiedSession = result.session;
        }
        // Keep server-verified flags during transient failures; same-generation
        // local profile edits are not authoritative permission updates.
        applySession(matchesVerifiedIdentity(current) ? verifiedSession : current);
        setUnverified(!matchesVerifiedIdentity(current));
      }
      setIsInitializing(false);
    };

    const handleAuthStateChange = () => void synchronize();
    const handleStorageChange = (event: StorageEvent) => {
      if (event.storageArea && event.storageArea !== localStorage) return;
      if (event.key !== null && event.key !== AUTH_SESSION_KEY) return;
      void synchronize();
    };
    window.addEventListener(
      AUTH_STATE_CHANGE_EVENT,
      handleAuthStateChange,
    );
    window.addEventListener('storage', handleStorageChange);
    void synchronize();
    return () => {
      active = false;
      syncSequence += 1;
      window.removeEventListener(
        AUTH_STATE_CHANGE_EVENT,
        handleAuthStateChange,
      );
      window.removeEventListener('storage', handleStorageChange);
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
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);
