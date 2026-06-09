import {render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {AuthProvider, useAuth} from '@/features/auth/components/AuthContext';
import {AUTH_STATE_CHANGE_EVENT} from '@/features/auth/components/context/shared';

const authContextMocks = vi.hoisted(() => ({
  actions: {
    clearError: vi.fn(),
    clearProfileCompletionRequirement: vi.fn(),
    confirmPasswordChange: vi.fn(),
    confirmPasswordReset: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
    register: vi.fn(),
    requestEmailAuthCode: vi.fn(),
    requestLoginCode: vi.fn(),
    requestPasswordChangeCode: vi.fn(),
    requestPasswordReset: vi.fn(),
    resendRegistrationCode: vi.fn(),
    verifyEmailAuthCode: vi.fn(),
    verifyLoginCode: vi.fn(),
    verifyPasswordChangeCode: vi.fn(),
    verifyPasswordResetCode: vi.fn(),
    verifyRegistrationCode: vi.fn(),
  },
  getStoredUser: vi.fn(),
  isAuthenticated: vi.fn(),
  isProfileCompletionRequired: vi.fn(),
}));

vi.mock('@/features/auth/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api')>('@/features/auth/api');
  return {
    ...actual,
    getStoredUser: authContextMocks.getStoredUser,
    isAuthenticated: authContextMocks.isAuthenticated,
    isProfileCompletionRequired: authContextMocks.isProfileCompletionRequired,
  };
});

vi.mock('@/features/auth/components/context/useAuthActions', () => ({
  useAuthActions: () => authContextMocks.actions,
}));

const Probe = () => {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="auth">{String(auth.isAuthenticated)}</span>
      <span data-testid="email">{auth.user?.email ?? 'none'}</span>
      <span data-testid="complete">{String(auth.requiresProfileCompletion)}</span>
      <button type="button" onClick={() => auth.clearError()}>clear</button>
    </div>
  );
};

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authContextMocks.getStoredUser.mockReturnValue({id: 1, email: 'member@example.com'});
    authContextMocks.isAuthenticated.mockReturnValue(true);
    authContextMocks.isProfileCompletionRequired.mockReturnValue(true);
  });

  it('initializes from stored auth and updates when auth state changes', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(screen.getByTestId('auth')).toHaveTextContent('true');
    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    expect(screen.getByTestId('complete')).toHaveTextContent('true');

    authContextMocks.getStoredUser.mockReturnValue(null);
    authContextMocks.isAuthenticated.mockReturnValue(false);
    window.dispatchEvent(new Event(AUTH_STATE_CHANGE_EVENT));

    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('false'));
    expect(screen.getByTestId('email')).toHaveTextContent('none');
    expect(screen.getByTestId('complete')).toHaveTextContent('false');
  });

  it('falls back to an unauthenticated default value when no provider is present', () => {
    render(<Probe />);

    expect(screen.getByTestId('auth')).toHaveTextContent('false');
  });
});
