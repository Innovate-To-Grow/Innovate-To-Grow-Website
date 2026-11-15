import {act, cleanup, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  expectFallback,
  httpError,
  NOTICE,
  renderPage,
  RETRY,
  STORED_SESSION,
} from '@/__tests__/routes/LoginLinkPage/fixtures/loginLinkPageFixtures';

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

describe('LoginLinkPage', () => {
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

  describe('a used link and the session stored in the browser', () => {
    const USED = httpError(400, {
      detail: 'This login link has already been used.',
      code: 'already_used',
      redirect_to: '/schedule',
    });

    beforeEach(() => {
      mockLoginLinkAutoLogin.mockRejectedValue(USED);
    });

    it('stays on "Signing you in..." while the session is checked, and exchanges the link only once', async () => {
      let settleCheck!: (value: unknown) => void;
      mockGetAccessToken.mockReturnValue('stored-access-token');
      mockBootstrapAuthSession.mockReturnValue(
        new Promise((resolve) => {
          settleCheck = resolve;
        }),
      );

      renderPage('/login-link?token=used123');

      await waitFor(() => {
        expect(mockBootstrapAuthSession).toHaveBeenCalledTimes(1);
      });
      expect(screen.getByText('Signing you in...')).toBeInTheDocument();
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(mockNavigate).not.toHaveBeenCalled();

      await act(async () => {
        settleCheck({status: 'anonymous', session: null});
      });

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(1);
      expect(mockBootstrapAuthSession).toHaveBeenCalledTimes(1);
    });

    it.each([
      ['verified', {status: 'verified', session: STORED_SESSION}],
      ['anonymous', {status: 'anonymous', session: null}],
    ])('does nothing with a %s answer that arrives after the page unmounted', async (_label, answer) => {
      let settleCheck!: (value: unknown) => void;
      mockGetAccessToken.mockReturnValue('stored-access-token');
      mockBootstrapAuthSession.mockReturnValue(
        new Promise((resolve) => {
          settleCheck = resolve;
        }),
      );
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

      const view = renderPage('/login-link?token=used123');
      await waitFor(() => {
        expect(mockBootstrapAuthSession).toHaveBeenCalledTimes(1);
      });
      view.unmount();
      await act(async () => {
        settleCheck(answer);
      });

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(errorSpy).not.toHaveBeenCalled();
      errorSpy.mockRestore();
    });

    it('falls back, with a retry, if the session check itself throws', async () => {
      mockGetAccessToken.mockReturnValue('stored-access-token');
      mockBootstrapAuthSession.mockRejectedValue(new Error('storage exploded'));

      const {container} = renderPage('/login-link?token=used123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.retryable);
      expect(screen.getByRole('button', {name: RETRY})).toBeInTheDocument();
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });
});
