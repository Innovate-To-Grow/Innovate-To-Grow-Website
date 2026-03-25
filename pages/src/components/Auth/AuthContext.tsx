import {
    createContext,
    useContext,
    useState,
    useEffect,
    useCallback,
    useMemo,
    type ReactNode,
} from 'react';
import {
    type User,
    type EmailAuthRequestResponse,
    type EmailAuthVerifyResponse,
    type LoginResponse,
    type RegisterResponse,
    type MessageResponse,
    type VerificationTokenResponse,
    clearProfileCompletionRequired as clearProfileCompletionRequiredStorage,
    isProfileCompletionRequired as checkProfileCompletionRequired,
    login as apiLogin,
    register as apiRegister,
    requestEmailAuthCode as apiRequestEmailAuthCode,
    requestLoginCode as apiRequestLoginCode,
    verifyEmailAuthCode as apiVerifyEmailAuthCode,
    verifyLoginCode as apiVerifyLoginCode,
    verifyRegistrationCode as apiVerifyRegistrationCode,
    resendRegistrationCode as apiResendRegistrationCode,
    requestPasswordReset as apiRequestPasswordReset,
    verifyPasswordResetCode as apiVerifyPasswordResetCode,
    confirmPasswordReset as apiConfirmPasswordReset,
    requestPasswordChangeCode as apiRequestPasswordChangeCode,
    verifyPasswordChangeCode as apiVerifyPasswordChangeCode,
    confirmPasswordChange as apiConfirmPasswordChange,
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
    requiresProfileCompletion: boolean;
    isLoading: boolean;
    error: string | null;

    // Auth actions
    login: (email: string, password: string) => Promise<LoginResponse>;
    register: (email: string, password: string, passwordConfirm: string, firstName?: string, lastName?: string, organization?: string) => Promise<RegisterResponse>;
    requestEmailAuthCode: (email: string) => Promise<EmailAuthRequestResponse>;
    verifyEmailAuthCode: (email: string, code: string) => Promise<EmailAuthVerifyResponse>;
    requestLoginCode: (email: string) => Promise<MessageResponse>;
    verifyLoginCode: (email: string, code: string) => Promise<LoginResponse>;
    verifyRegistrationCode: (email: string, code: string) => Promise<LoginResponse>;
    resendRegistrationCode: (email: string) => Promise<MessageResponse>;
    requestPasswordReset: (email: string) => Promise<MessageResponse>;
    verifyPasswordResetCode: (email: string, code: string) => Promise<VerificationTokenResponse>;
    confirmPasswordReset: (email: string, verificationToken: string, newPassword: string, confirmPassword: string) => Promise<MessageResponse>;
    requestPasswordChangeCode: (email: string) => Promise<MessageResponse>;
    verifyPasswordChangeCode: (email: string, code: string) => Promise<VerificationTokenResponse>;
    confirmPasswordChange: (verificationToken: string, newPassword: string, confirmPassword: string) => Promise<MessageResponse>;
    logout: () => void;
    refreshProfile: () => Promise<void>;
    clearProfileCompletionRequirement: () => void;
    clearError: () => void;
}

const defaultContextValue: AuthContextValue = {
    user: null,
    isAuthenticated: false,
    requiresProfileCompletion: false,
    isLoading: true,
    error: null,
    login: async () => {
        throw new Error('Not implemented');
    },
    register: async () => {
        throw new Error('Not implemented');
    },
    requestEmailAuthCode: async () => {
        throw new Error('Not implemented');
    },
    verifyEmailAuthCode: async () => {
        throw new Error('Not implemented');
    },
    requestLoginCode: async () => {
        throw new Error('Not implemented');
    },
    verifyLoginCode: async () => {
        throw new Error('Not implemented');
    },
    verifyRegistrationCode: async () => {
        throw new Error('Not implemented');
    },
    resendRegistrationCode: async () => {
        throw new Error('Not implemented');
    },
    requestPasswordReset: async () => {
        throw new Error('Not implemented');
    },
    verifyPasswordResetCode: async () => {
        throw new Error('Not implemented');
    },
    confirmPasswordReset: async () => {
        throw new Error('Not implemented');
    },
    requestPasswordChangeCode: async () => {
        throw new Error('Not implemented');
    },
    verifyPasswordChangeCode: async () => {
        throw new Error('Not implemented');
    },
    confirmPasswordChange: async () => {
        throw new Error('Not implemented');
    },
    logout: () => {
    },
    refreshProfile: async () => {
    },
    clearProfileCompletionRequirement: () => {
    },
    clearError: () => {
    },
};

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

    const clearError = useCallback(() => {
        setError(null);
    }, []);

    const runWithErrorHandling = useCallback(async <T, >(callback: () => Promise<T>): Promise<T> => {
        setError(null);
        setIsLoading(true);
        try {
            return await callback();
        } catch (err: unknown) {
            const message = getErrorMessage(err);
            setError(message);
            throw err;
        } finally {
            setIsLoading(false);
        }
    }, []);

    const login = useCallback(async (email: string, password: string): Promise<LoginResponse> => {
        return runWithErrorHandling(async () => {
            const response = await apiLogin(email, password);
            setUser(response.user);
            setRequiresProfileCompletion(false);
            dispatchAuthStateChange();
            return response;
        });
    }, [runWithErrorHandling]);

    const register = useCallback(async (
        email: string,
        password: string,
        passwordConfirm: string,
        firstName?: string,
        lastName?: string,
        organization?: string,
    ): Promise<RegisterResponse> => {
        return runWithErrorHandling(() => apiRegister(email, password, passwordConfirm, firstName, lastName, organization));
    }, [runWithErrorHandling]);

    const requestEmailAuthCode = useCallback(async (email: string): Promise<EmailAuthRequestResponse> => {
        return runWithErrorHandling(() => apiRequestEmailAuthCode(email));
    }, [runWithErrorHandling]);

    const verifyEmailAuthCode = useCallback(async (email: string, code: string): Promise<EmailAuthVerifyResponse> => {
        return runWithErrorHandling(async () => {
            const response = await apiVerifyEmailAuthCode(email, code);
            setUser(response.user);
            setRequiresProfileCompletion(response.requires_profile_completion);
            dispatchAuthStateChange();
            return response;
        });
    }, [runWithErrorHandling]);

    const requestLoginCode = useCallback(async (email: string): Promise<MessageResponse> => {
        return runWithErrorHandling(() => apiRequestLoginCode(email));
    }, [runWithErrorHandling]);

    const verifyLoginCode = useCallback(async (email: string, code: string): Promise<LoginResponse> => {
        return runWithErrorHandling(async () => {
            const response = await apiVerifyLoginCode(email, code);
            setUser(response.user);
            setRequiresProfileCompletion(false);
            dispatchAuthStateChange();
            return response;
        });
    }, [runWithErrorHandling]);

    const verifyRegistrationCode = useCallback(async (email: string, code: string): Promise<LoginResponse> => {
        return runWithErrorHandling(async () => {
            const response = await apiVerifyRegistrationCode(email, code);
            setUser(response.user);
            setRequiresProfileCompletion(false);
            dispatchAuthStateChange();
            return response;
        });
    }, [runWithErrorHandling]);

    const resendRegistrationCode = useCallback(async (email: string): Promise<MessageResponse> => {
        return runWithErrorHandling(() => apiResendRegistrationCode(email));
    }, [runWithErrorHandling]);

    const requestPasswordReset = useCallback(async (email: string): Promise<MessageResponse> => {
        return runWithErrorHandling(() => apiRequestPasswordReset(email));
    }, [runWithErrorHandling]);

    const verifyPasswordResetCode = useCallback(async (
        email: string,
        code: string,
    ): Promise<VerificationTokenResponse> => {
        return runWithErrorHandling(() => apiVerifyPasswordResetCode(email, code));
    }, [runWithErrorHandling]);

    const confirmPasswordReset = useCallback(async (
        email: string,
        verificationToken: string,
        newPassword: string,
        confirmPassword: string,
    ): Promise<MessageResponse> => {
        return runWithErrorHandling(() => apiConfirmPasswordReset(email, verificationToken, newPassword, confirmPassword));
    }, [runWithErrorHandling]);

    const requestPasswordChangeCode = useCallback(async (email: string): Promise<MessageResponse> => {
        return runWithErrorHandling(() => apiRequestPasswordChangeCode(email));
    }, [runWithErrorHandling]);

    const verifyPasswordChangeCode = useCallback(async (
        email: string,
        code: string,
    ): Promise<VerificationTokenResponse> => {
        return runWithErrorHandling(() => apiVerifyPasswordChangeCode(email, code));
    }, [runWithErrorHandling]);

    const confirmPasswordChange = useCallback(async (
        verificationToken: string,
        newPassword: string,
        confirmPassword: string,
    ): Promise<MessageResponse> => {
        return runWithErrorHandling(() => apiConfirmPasswordChange(verificationToken, newPassword, confirmPassword));
    }, [runWithErrorHandling]);

    const logout = useCallback(() => {
        apiLogout();
        setUser(null);
        setRequiresProfileCompletion(false);
        dispatchAuthStateChange();
    }, []);

    const clearProfileCompletionRequirement = useCallback(() => {
        clearProfileCompletionRequiredStorage();
        setRequiresProfileCompletion(false);
        dispatchAuthStateChange();
    }, []);

    const refreshProfile = useCallback(async () => {
        if (!checkIsAuthenticated()) return;
        try {
            const profile = await apiGetProfile();
            setUser(prev => {
                if (!prev) return null;
                const nextUser = {
                    ...prev,
                    profile_image: profile.profile_image,
                };
                localStorage.setItem('i2g_user', JSON.stringify(nextUser));
                return nextUser;
            });
        } catch {
            // Silently fail - user might be logged out
        }
    }, []);

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

// ======================== Helpers ========================

function looksLikeHtml(value: string): boolean {
    return /^\s*<!DOCTYPE/i.test(value) || /<[a-z][\s\S]*>/i.test(value);
}

function isSafeMessage(value: string): boolean {
    return value.length <= 300 && !looksLikeHtml(value);
}

function getErrorMessage(err: unknown): string {
    if (typeof err === 'object' && err !== null) {
        const axiosError = err as { response?: { status?: number; data?: Record<string, unknown> } };
        if (axiosError.response?.data) {
            const data = axiosError.response.data;
            const messages: string[] = [];
            for (const value of Object.values(data)) {
                if (Array.isArray(value)) {
                    for (const item of value) {
                        if (typeof item === 'string' && isSafeMessage(item)) messages.push(item);
                    }
                } else if (typeof value === 'string' && isSafeMessage(value)) {
                    messages.push(value);
                }
            }
            if (messages.length > 0) return messages.join(' ');

            const status = axiosError.response.status;
            if (status && status >= 400 && status < 500) {
                return 'Request failed. Please check your input and try again.';
            }
            if (status && status >= 500) {
                return 'A server error occurred. Please try again later.';
            }
        }
    }
    return 'An unexpected error occurred. Please try again.';
}
