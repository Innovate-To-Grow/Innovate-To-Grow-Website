import {
    useEffect,
    useState,
    useMemo,
    createContext,
    useContext,
    type ReactNode,
} from 'react';
import {
    type User,
    isProfileCompletionRequired as checkProfileCompletionRequired,
    getStoredUser,
    isAuthenticated as checkIsAuthenticated,
} from '../../services/auth';
import { AUTH_STATE_CHANGE_EVENT, defaultContextValue, type AuthContextValue } from './context/shared';
import { useAuthActions } from './context/useAuthActions';

const AuthContext = createContext<AuthContextValue>(defaultContextValue);

// ======================== Provider ========================

interface AuthProviderProps {
    children: ReactNode;
}

export const AuthProvider = ({children}: AuthProviderProps) => {
    const [user, setUser] = useState<User | null>(null);
    const [requiresProfileCompletion, setRequiresProfileCompletion] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Initialize auth state from localStorage
    useEffect(() => {
        const storedUser = getStoredUser();
        if (storedUser && checkIsAuthenticated()) {
            setUser(storedUser);
            setRequiresProfileCompletion(checkProfileCompletionRequired());
        } else {
            setRequiresProfileCompletion(false);
        }
        setIsLoading(false);
    }, []);

    // Listen for auth state changes from other React roots
    useEffect(() => {
        const handleAuthStateChange = () => {
            const storedUser = getStoredUser();
            if (storedUser && checkIsAuthenticated()) {
                setUser(storedUser);
                setRequiresProfileCompletion(checkProfileCompletionRequired());
            } else {
                setUser(null);
                setRequiresProfileCompletion(false);
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

    const {
        clearError,
        login,
        register,
        requestEmailAuthCode,
        verifyEmailAuthCode,
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

    const value: AuthContextValue = useMemo(() => ({
        user,
        isAuthenticated: !!user,
        requiresProfileCompletion,
        isLoading,
        error,
        login,
        register,
        requestEmailAuthCode,
        verifyEmailAuthCode,
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
    }), [
        user,
        requiresProfileCompletion,
        isLoading,
        error,
        login,
        register,
        requestEmailAuthCode,
        verifyEmailAuthCode,
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
    ]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// ======================== Hook ========================

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);
