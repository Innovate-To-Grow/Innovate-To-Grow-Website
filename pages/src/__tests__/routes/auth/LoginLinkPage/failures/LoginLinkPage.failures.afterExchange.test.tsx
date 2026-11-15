import {act, cleanup, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  expectFallback,
  handoffToken,
  NOTICE,
  renderPage,
  seedHandoff,
  STORED_SESSION,
} from '@/__tests__/routes/auth/LoginLinkPage/fixtures/loginLinkPageFixtures';

const mockLoginLinkAutoLogin = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();
const mockGetAccessToken = vi.fn();
const mockBootstrapAuthSession = vi.fn();
const mockUseAuth = vi.fn();

vi.mock('@/features/auth/api/signin/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/signin/session')>()),
  loginLinkAutoLogin: (...args: unknown[]) => mockLoginLinkAutoLogin(...args),
  bootstrapAuthSession: () => mockBootstrapAuthSession(),
}));

vi.mock('@/features/auth/api/session/storage', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/session/storage')>()),
  getAccessToken: () => mockGetAccessToken(),
}));

vi.mock('@/features/auth/components/context/shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/components/context/shared')>()),
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

// The fallback's own behaviour is covered in LoginLinkFallback.test.tsx and, end
// to end with the real provider, in LoginLinkPage.integration.test.tsx.
vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const LOGIN_RESPONSE = {
  message: 'Login successful.',
  access: 'access-token',
  refresh: 'refresh-token',
  user: {member_uuid: '123', email: 'ada@example.com'},
  redirect_to: '/schedule',
};

const buildAuth = (overrides: Record<string, unknown> = {}) => ({
  isAuthenticated: false,
  requiresProfileCompletion: false,
  error: null,
  isLoading: false,
  // The unified flow creates an account for an unknown address; it must stay unused.
  requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'Check your email for a verification code.'}),
  verifyEmailAuthCode: vi.fn(),
  clearError: vi.fn(),
  verifyLoginCode: vi.fn(),
  verifyRegistrationCode: vi.fn(),
  resendRegistrationCode: vi.fn(),
  requestLoginCode: vi
    .fn()
    .mockResolvedValue({message: 'If an eligible account exists, a verification code has been sent.'}),
  requestPasswordReset: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  confirmPasswordReset: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  verifyPasswordChangeCode: vi.fn(),
  confirmPasswordChange: vi.fn(),
  ...overrides,
});

describe('LoginLinkPage — failures during and after the exchange', () => {
  beforeEach(() => {
    mockLoginLinkAutoLogin.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
    mockGetAccessToken.mockReset();
    mockGetAccessToken.mockReturnValue(null);
    mockBootstrapAuthSession.mockReset();
    mockBootstrapAuthSession.mockResolvedValue({status: 'verified', session: STORED_SESSION});
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(buildAuth());
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    cleanup();
  });

  describe('a page that unmounts mid-exchange', () => {
    it('does not navigate after a late success, but still drops the spent token', async () => {
      let resolveExchange!: (value: typeof LOGIN_RESPONSE) => void;
      mockLoginLinkAutoLogin.mockReturnValue(
        new Promise((resolve) => {
          resolveExchange = resolve;
        }),
      );
      seedHandoff('late123');

      const view = renderPage('/login-link');
      await waitFor(() => {
        expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('late123');
      });
      view.unmount();
      await act(async () => {
        resolveExchange(LOGIN_RESPONSE);
      });

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
      expect(handoffToken()).toBeNull();
    });
  });

  describe('a step after the exchange that throws', () => {
    it.each([
      ['navigate', () => mockNavigate.mockImplementationOnce(() => {
        throw new Error('router exploded');
      })],
      ['the auth-state event', () => mockDispatchAuthStateChange.mockImplementationOnce(() => {
        throw new Error('listener exploded');
      })],
    ])('never leaves the page on "Signing you in..." when %s throws', async (_label, arrange) => {
      arrange();
      mockLoginLinkAutoLogin.mockResolvedValue(LOGIN_RESPONSE);
      seedHandoff('boom123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expect(screen.queryByText('Signing you in...')).toBeNull();
      expectFallback(container, NOTICE.retryable);
      // The exchange itself succeeded, so its token is spent and not retained.
      expect(handoffToken()).toBeNull();
    });

    it('runs nothing after the exchange once the page has unmounted, even if a step would throw', async () => {
      let resolveExchange!: (value: typeof LOGIN_RESPONSE) => void;
      mockLoginLinkAutoLogin.mockReturnValue(
        new Promise((resolve) => {
          resolveExchange = resolve;
        }),
      );
      // Would throw if reached: the page must return before dispatching at all.
      mockDispatchAuthStateChange.mockImplementation(() => {
        throw new Error('listener exploded');
      });
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

      const view = renderPage('/login-link?token=gone123');
      await waitFor(() => {
        expect(mockLoginLinkAutoLogin).toHaveBeenCalled();
      });
      view.unmount();
      await act(async () => {
        resolveExchange(LOGIN_RESPONSE);
      });

      expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(errorSpy).not.toHaveBeenCalled();
      errorSpy.mockRestore();
    });
  });
});
