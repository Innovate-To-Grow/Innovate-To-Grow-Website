import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {getStoredSession, type StoredAuthSession, type User} from '@/features/auth/api';
import {defaultContextValue, type AuthContextValue} from './context/shared';
import {useAuthActions} from './context/useAuthActions';
import {useSessionSynchronization} from './context/useSessionSynchronization';

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

  useSessionSynchronization({applySession, setUnverified, setIsInitializing});

  const actions = useAuthActions({
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
      ...actions,
    }),
    [
      user,
      unverified,
      isInitializing,
      requiresProfileCompletion,
      isLoading,
      error,
      actions,
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
