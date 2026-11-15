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
  authStorageEvent,
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

  it.each(['verified', 'unverified'] as const)(
    'keeps a verified generation signed in through a background check returning %s',
    async (status) => {
      authApi.getStoredSession.mockReturnValue(session);
      authApi.bootstrapAuthSession.mockResolvedValueOnce(verifiedSession);
      render(<AuthProvider><AuthState /></AuthProvider>);
      await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));

      const pending = deferredBootstrap();
      const refreshed = {...session, access: 'access-2', refresh: 'refresh-2'};
      authApi.getStoredSession.mockReturnValue(refreshed);
      authApi.bootstrapAuthSession.mockReturnValueOnce(pending.promise);
      act(() => window.dispatchEvent(new Event('i2g-auth-state-change')));
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
      expect(screen.getByTestId('initializing')).toHaveTextContent('false');
      await act(async () => pending.resolve({status, session: refreshed}));
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
      expect(screen.getByTestId('unverified')).toHaveTextContent('false');
    },
  );

  it('synchronizes profile changes without signing out and ignores unrelated storage', async () => {
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockResolvedValueOnce(verifiedSession);
    render(<AuthProvider><AuthState /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));
    act(() => {
      window.dispatchEvent(storageEvent('theme'));
      window.dispatchEvent(storageEvent('i2g_auth_session', sessionStorage));
    });
    expect(authApi.bootstrapAuthSession).toHaveBeenCalledOnce();

    const pending = deferredBootstrap();
    const updated = {...session, user: {...user, email: 'updated@example.com'}};
    authApi.getStoredSession.mockReturnValue(updated);
    authApi.bootstrapAuthSession.mockReturnValueOnce(pending.promise);
    act(() => window.dispatchEvent(authStorageEvent()));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    await act(async () => pending.resolve({status: 'verified', session: updated}));
    expect(screen.getByTestId('email')).toHaveTextContent('updated@example.com');
  });

  it('gates a replacement account and ignores the old initial bootstrap completion', async () => {
    const initial = deferredBootstrap();
    const replacement = deferredBootstrap();
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockReturnValueOnce(initial.promise).mockReturnValueOnce(replacement.promise);
    render(<AuthProvider><AuthState /></AuthProvider>);

    const next = {...session, generation: 'generation-2', user: {...user, member_uuid: 'member-2', email: 'next@example.com'}};
    authApi.getStoredSession.mockReturnValue(next);
    act(() => window.dispatchEvent(authStorageEvent()));
    expect(screen.getByTestId('email')).toHaveTextContent('next@example.com');
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    expect(screen.getByTestId('initializing')).toHaveTextContent('true');
    await act(async () => replacement.resolve({status: 'verified', session: next}));
    await act(async () => initial.resolve(verifiedSession));
    expect(screen.getByTestId('email')).toHaveTextContent('next@example.com');
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
  });

  it('does not reuse a verified account for an unverified replacement', async () => {
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockResolvedValueOnce(verifiedSession);
    render(<AuthProvider><AuthState /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));
    const next = {...session, generation: 'generation-2', user: {...user, member_uuid: 'member-2'}};
    authApi.getStoredSession.mockReturnValue(next);
    authApi.bootstrapAuthSession.mockResolvedValueOnce({status: 'unverified', session: next});
    await act(async () => window.dispatchEvent(authStorageEvent()));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    expect(screen.getByTestId('unverified')).toHaveTextContent('true');
  });

  it('retains verified profile requirements after unverified same-generation storage changes', async () => {
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockResolvedValueOnce(verifiedSession);
    render(<AuthProvider><AuthState /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));
    const pending = deferredBootstrap();
    const changed = {...session, requires_profile_completion: false, user: {...user, email: 'unverified@example.com'}};
    authApi.getStoredSession.mockReturnValue(changed);
    authApi.bootstrapAuthSession.mockReturnValueOnce(pending.promise);
    act(() => window.dispatchEvent(authStorageEvent()));
    expect(screen.getByTestId('profile-required')).toHaveTextContent('true');
    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    await act(async () => pending.resolve({status: 'unverified', session: changed}));
    expect(screen.getByTestId('profile-required')).toHaveTextContent('true');
    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
  });

  it('does not accept a verification result for another identity', async () => {
    const other = {...session, generation: 'generation-other', user: {...user, member_uuid: 'other-member'}};
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockResolvedValueOnce({status: 'verified', session: other});
    render(<AuthProvider><AuthState /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
  });
});
