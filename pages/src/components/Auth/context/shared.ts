import type {
  EmailAuthSource,
  EmailAuthRequestResponse,
  EmailAuthVerifyResponse,
  LoginResponse,
  MessageResponse,
  RegisterResponse,
  User,
  VerificationTokenResponse,
} from '../../../services/auth';

export const AUTH_STATE_CHANGE_EVENT = 'i2g-auth-state-change';

export const dispatchAuthStateChange = () => {
  window.dispatchEvent(new CustomEvent(AUTH_STATE_CHANGE_EVENT));
};

export interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  requiresProfileCompletion: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<LoginResponse>;
  register: (email: string, password: string, passwordConfirm: string, firstName: string, lastName: string, organization: string, title?: string) => Promise<RegisterResponse>;
  requestEmailAuthCode: (email: string, source?: EmailAuthSource) => Promise<EmailAuthRequestResponse>;
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

const notImplemented = async () => {
  throw new Error('Not implemented');
};

export const defaultContextValue: AuthContextValue = {
  user: null,
  isAuthenticated: false,
  requiresProfileCompletion: false,
  isLoading: true,
  error: null,
  login: notImplemented,
  register: notImplemented,
  requestEmailAuthCode: notImplemented,
  verifyEmailAuthCode: notImplemented,
  requestLoginCode: notImplemented,
  verifyLoginCode: notImplemented,
  verifyRegistrationCode: notImplemented,
  resendRegistrationCode: notImplemented,
  requestPasswordReset: notImplemented,
  verifyPasswordResetCode: notImplemented,
  confirmPasswordReset: notImplemented,
  requestPasswordChangeCode: notImplemented,
  verifyPasswordChangeCode: notImplemented,
  confirmPasswordChange: notImplemented,
  logout: () => {},
  refreshProfile: async () => {},
  clearProfileCompletionRequirement: () => {},
  clearError: () => {},
};

function looksLikeHtml(value: string): boolean {
  return /^\s*<!DOCTYPE/i.test(value) || /<[a-z][\s\S]*>/i.test(value);
}

/** Check that a string is short enough and free of HTML before displaying to a user. */
export function isSafeMessage(value: string): boolean {
  return value.length <= 300 && !looksLikeHtml(value);
}

export function getAuthErrorMessage(err: unknown): string {
  if (typeof err !== 'object' || err === null) {
    return 'An unexpected error occurred. Please try again.';
  }
  const axiosError = err as { response?: { status?: number; data?: Record<string, unknown> } };
  if (!axiosError.response?.data) {
    return 'An unexpected error occurred. Please try again.';
  }
  const messages: string[] = [];
  for (const value of Object.values(axiosError.response.data)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === 'string' && isSafeMessage(item)) messages.push(item);
      }
    } else if (typeof value === 'string' && isSafeMessage(value)) {
      messages.push(value);
    }
  }
  if (messages.length > 0) return messages.join(' ');
  if (axiosError.response.status && axiosError.response.status >= 400 && axiosError.response.status < 500) {
    return 'Request failed. Please check your input and try again.';
  }
  if (axiosError.response.status && axiosError.response.status >= 500) {
    return 'A server error occurred. Please try again later.';
  }
  return 'An unexpected error occurred. Please try again.';
}
