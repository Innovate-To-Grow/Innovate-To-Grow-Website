import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
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
  deferredBootstrap,
  session,
  storageEvent,
  user,
  verifiedSession,
} from '@/__tests__/features/auth/components/AuthContext/authContextFixtures';

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

  it('verifies a replacement that arrived before its storage event', async () => {
    const initial = deferredBootstrap();
    const replacement = deferredBootstrap();
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockReturnValueOnce(initial.promise).mockReturnValueOnce(replacement.promise);
    render(<AuthProvider><AuthState /></AuthProvider>);
    const next = {...session, generation: 'generation-2', user: {...user, member_uuid: 'member-2'}};
    authApi.getStoredSession.mockReturnValue(next);
    await act(async () => initial.resolve({status: 'unverified', session: next}));
    expect(authApi.bootstrapAuthSession).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    await act(async () => replacement.resolve({status: 'verified', session: next}));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
  });

  it.each(['logout', 'rejection'])(
    'clears an established session on %s and cannot resurrect it from an older check',
    async (reason) => {
      authApi.getStoredSession.mockReturnValue(session);
      authApi.bootstrapAuthSession.mockResolvedValueOnce(verifiedSession);
      render(<AuthProvider><AuthState /></AuthProvider>);
      await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));
      const pending = deferredBootstrap();
      authApi.bootstrapAuthSession.mockReturnValueOnce(pending.promise);
      act(() => window.dispatchEvent(new Event('i2g-auth-state-change')));
      authApi.getStoredSession.mockReturnValue(null);
      if (reason === 'logout') {
        act(() => window.dispatchEvent(storageEvent(null)));
        await act(async () => pending.resolve(verifiedSession));
      } else {
        await act(async () => pending.resolve(anonymousSession));
      }
      expect(screen.getByTestId('email')).toHaveTextContent('anonymous');
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
      expect(screen.getByTestId('initializing')).toHaveTextContent('false');
    },
  );

  it('retries a transient verification failure until the session verifies', async () => {
    vi.useFakeTimers();
    try {
      authApi.getStoredSession.mockReturnValue(session);
      authApi.bootstrapAuthSession.mockResolvedValueOnce({status: 'unverified', session});
      render(<AuthProvider><AuthState /></AuthProvider>);
      await act(async () => { await Promise.resolve(); });

      // A transient failure keeps the identity but cannot authenticate it.
      expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
      const callsAfterFailure = authApi.bootstrapAuthSession.mock.calls.length;

      // Nothing else re-runs the check, so the provider must do it itself.
      authApi.bootstrapAuthSession.mockResolvedValue(verifiedSession);
      await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });

      expect(authApi.bootstrapAuthSession.mock.calls.length).toBeGreaterThan(callsAfterFailure);
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not retry after a confirmed sign-out', async () => {
    vi.useFakeTimers();
    try {
      authApi.getStoredSession.mockReturnValue(session);
      authApi.bootstrapAuthSession.mockResolvedValue(anonymousSession);
      render(<AuthProvider><AuthState /></AuthProvider>);
      await act(async () => { await Promise.resolve(); });
      const calls = authApi.bootstrapAuthSession.mock.calls.length;

      await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

      expect(authApi.bootstrapAuthSession).toHaveBeenCalledTimes(calls);
      expect(screen.getByTestId('email')).toHaveTextContent('anonymous');
    } finally {
      vi.useRealTimers();
    }
  });

  it('stops retrying once unmounted', async () => {
    vi.useFakeTimers();
    try {
      authApi.getStoredSession.mockReturnValue(session);
      authApi.bootstrapAuthSession.mockResolvedValue({status: 'unverified', session});
      const {unmount} = render(<AuthProvider><AuthState /></AuthProvider>);
      await act(async () => { await Promise.resolve(); });
      const calls = authApi.bootstrapAuthSession.mock.calls.length;

      unmount();
      await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

      expect(authApi.bootstrapAuthSession).toHaveBeenCalledTimes(calls);
    } finally {
      vi.useRealTimers();
    }
  });
});
