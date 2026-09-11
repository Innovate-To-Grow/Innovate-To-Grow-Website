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

const user = {
  member_uuid: '978b882b-d693-4e5e-aee1-21ff69ac82a4',
  email: 'member@example.com',
};
const session = {
  version: 1 as const,
  access: 'access-1',
  refresh: 'refresh-1',
  user,
  generation: 'generation-1',
  requires_profile_completion: true,
};

const verifiedSession = {status: 'verified' as const, session};
const anonymousSession = {status: 'anonymous' as const, session: null};
type BootstrapResult = typeof anonymousSession | {status: 'verified' | 'unverified'; session: typeof session};
const deferredBootstrap = () => {
  let resolve!: (result: BootstrapResult) => void;
  const promise = new Promise<BootstrapResult>((done) => { resolve = done; });
  return {promise, resolve};
};
const storageEvent = (key: string | null, storageArea = localStorage) => {
  const event = new StorageEvent('storage', {key});
  Object.defineProperty(event, 'storageArea', {value: storageArea});
  return event;
};
const authStorageEvent = () => storageEvent('i2g_auth_session');

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

  it('renders children from the guarded stored session while bootstrap verifies it', async () => {
    let resolveBootstrap: (value: typeof verifiedSession) => void = () =>
      undefined;
    authApi.bootstrapAuthSession.mockReturnValue(
      new Promise((resolve) => {
        resolveBootstrap = resolve;
      }),
    );
    authApi.getStoredSession.mockReturnValue(session);

    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );

    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    expect(screen.getByTestId('initializing')).toHaveTextContent('true');
    expect(screen.getByTestId('unverified')).toHaveTextContent('true');
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    await act(async () => resolveBootstrap(verifiedSession));

    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    expect(screen.getByTestId('profile-required')).toHaveTextContent('true');
    expect(screen.getByTestId('initializing')).toHaveTextContent('false');
    expect(screen.getByTestId('unverified')).toHaveTextContent('false');
    expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
  });

  it.each(['i2g-auth-state-change', 'storage'])(
    'synchronizes an authenticated session on %s',
    async (eventName) => {
      authApi.getStoredSession.mockReturnValue(null);
      render(
        <AuthProvider>
          <AuthState />
        </AuthProvider>,
      );
      await screen.findByText('anonymous');

      authApi.getStoredSession.mockReturnValue(session);
      authApi.bootstrapAuthSession.mockResolvedValue(verifiedSession);
      act(() => window.dispatchEvent(eventName === 'storage' ? authStorageEvent() : new Event(eventName)));

      await waitFor(() =>
        expect(screen.getByTestId('email')).toHaveTextContent(
          'member@example.com',
        ),
      );
      expect(authApi.bootstrapAuthSession).toHaveBeenCalledOnce();
    },
  );

  it('clears local state when another root logs out', async () => {
    authApi.getStoredSession.mockReturnValue(session);
    authApi.bootstrapAuthSession.mockResolvedValueOnce(verifiedSession);
    const {unmount} = render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );
    await screen.findByText('member@example.com');
    authApi.getStoredSession.mockReturnValue(null);

    act(() => window.dispatchEvent(new Event('i2g-auth-state-change')));

    expect(screen.getByTestId('email')).toHaveTextContent('anonymous');
    expect(screen.getByTestId('profile-required')).toHaveTextContent('false');
    unmount();
  });

  it('ignores an in-flight synchronization after unmount and removes listeners', async () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    let resolveSync: (value: typeof verifiedSession) => void = () =>
      undefined;
    authApi.getStoredSession.mockReturnValue(session);
    authApi.isAuthenticated.mockReturnValue(false);
    authApi.bootstrapAuthSession
      .mockResolvedValueOnce(anonymousSession)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveSync = resolve;
        }),
      );
    const {unmount} = render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );
    await screen.findByText('anonymous');

    act(() => window.dispatchEvent(authStorageEvent()));
    unmount();
    await act(async () => resolveSync(verifiedSession));

    expect(removeSpy).toHaveBeenCalledWith(
      'i2g-auth-state-change',
      expect.any(Function),
    );
    expect(removeSpy).toHaveBeenCalledWith('storage', expect.any(Function));
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
