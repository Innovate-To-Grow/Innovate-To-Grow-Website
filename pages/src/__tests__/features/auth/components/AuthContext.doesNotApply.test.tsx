import {
  act,
  cleanup,
  render,
  screen,
} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const authApi = vi.hoisted(() => ({
  bootstrapAuthSession: vi.fn(),
  getStoredSession: vi.fn(),
  isAuthenticated: vi.fn(),
}));

vi.mock('@/features/auth/api', () => authApi);
vi.mock('@/features/auth/components/context/useAuthActions', () => ({
  useAuthActions: () => ({
    clearError: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    requestEmailAuthCode: vi.fn(),
    verifyEmailAuthCode: vi.fn(),
    requestPhoneAuthCode: vi.fn(),
    verifyPhoneAuthCode: vi.fn(),
    requestLoginCode: vi.fn(),
    verifyLoginCode: vi.fn(),
    verifyRegistrationCode: vi.fn(),
    resendRegistrationCode: vi.fn(),
    requestPasswordReset: vi.fn(),
    verifyPasswordResetCode: vi.fn(),
    confirmPasswordReset: vi.fn(),
    requestPasswordChangeCode: vi.fn(),
    verifyPasswordChangeCode: vi.fn(),
    confirmPasswordChange: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
    clearProfileCompletionRequirement: vi.fn(),
  }),
}));

import {AuthProvider, useAuth} from '@/features/auth/components/AuthContext';
import {
  anonymousSession,
  session,
  verifiedSession,
} from '@/__tests__/features/auth/components/authContextFixtures';

function AuthState() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="email">{auth.user?.email ?? 'anonymous'}</span>
      <span data-testid="profile-required">
        {String(auth.requiresProfileCompletion)}
      </span>
      <span data-testid="initializing">{String(auth.isInitializing)}</span>
      <span data-testid="unverified">{String(auth.unverified)}</span>
      <span data-testid="authenticated">{String(auth.isAuthenticated)}</span>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    authApi.bootstrapAuthSession.mockResolvedValue(anonymousSession);
    authApi.getStoredSession.mockReturnValue(null);
    authApi.isAuthenticated.mockReturnValue(false);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('does not apply bootstrap completion after unmount', async () => {
    let resolveBootstrap: (value: typeof verifiedSession) => void = () =>
      undefined;
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockReturnValue(
      new Promise((resolve) => {
        resolveBootstrap = resolve;
      }),
    );
    const {unmount} = render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );

    unmount();
    await act(async () => resolveBootstrap(verifiedSession));

    expect(screen.queryByTestId('email')).toBeNull();
  });
});
