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

const user = {
  id: '978b882b-d693-4e5e-aee1-21ff69ac82a4',
  email: 'member@example.com',
};
const session = {
  user,
  generation: 'generation-1',
  requires_profile_completion: true,
};

function AuthState() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="email">{auth.user?.email ?? 'anonymous'}</span>
      <span data-testid="profile-required">
        {String(auth.requiresProfileCompletion)}
      </span>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authApi.bootstrapAuthSession.mockResolvedValue(null);
    authApi.getStoredSession.mockReturnValue(null);
    authApi.isAuthenticated.mockReturnValue(false);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('hides children until bootstrap and applies the stored session', async () => {
    let resolveBootstrap: (value: typeof session) => void = () => undefined;
    authApi.bootstrapAuthSession.mockReturnValue(
      new Promise((resolve) => {
        resolveBootstrap = resolve;
      }),
    );

    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );

    expect(screen.queryByTestId('email')).not.toBeInTheDocument();
    await act(async () => resolveBootstrap(session));

    expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
    expect(screen.getByTestId('profile-required')).toHaveTextContent('true');
  });

  it.each(['i2g-auth-state-change', 'storage'])(
    'synchronizes an authenticated session on %s',
    async (eventName) => {
      authApi.getStoredSession.mockReturnValue(session);
      authApi.isAuthenticated.mockReturnValue(true);
      render(
        <AuthProvider>
          <AuthState />
        </AuthProvider>,
      );
      await screen.findByText('anonymous');

      act(() => window.dispatchEvent(new Event(eventName)));

      expect(screen.getByTestId('email')).toHaveTextContent('member@example.com');
      expect(authApi.bootstrapAuthSession).toHaveBeenCalledOnce();
    },
  );

  it('clears local state when another root logs out', async () => {
    authApi.bootstrapAuthSession.mockResolvedValueOnce(session);
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
    let resolveSync: (value: typeof session) => void = () => undefined;
    authApi.getStoredSession.mockReturnValue(session);
    authApi.isAuthenticated.mockReturnValue(false);
    authApi.bootstrapAuthSession
      .mockResolvedValueOnce(null)
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

    act(() => window.dispatchEvent(new Event('storage')));
    unmount();
    await act(async () => resolveSync(session));

    expect(removeSpy).toHaveBeenCalledWith(
      'i2g-auth-state-change',
      expect.any(Function),
    );
    expect(removeSpy).toHaveBeenCalledWith('storage', expect.any(Function));
  });

  it('does not apply bootstrap completion after unmount', async () => {
    let resolveBootstrap: (value: typeof session) => void = () => undefined;
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
    await act(async () => resolveBootstrap(session));

    expect(screen.queryByTestId('email')).toBeNull();
  });
});
