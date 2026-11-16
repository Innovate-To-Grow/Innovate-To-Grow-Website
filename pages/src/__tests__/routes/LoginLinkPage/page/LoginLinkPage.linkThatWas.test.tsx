import {cleanup, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  expectFallback,
  handoffToken,
  httpError,
  NOTICE,
  renderPage,
  RETRY,
  seedHandoff,
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

  describe('a link that was already used', () => {
    it.each([
      ['machine-readable code', {detail: 'Link was consumed.', code: 'already_used'}],
      ['detail text from an older backend', {detail: 'This login link has already been used.'}],
    ])('continues to /account when a session is stored (%s)', async (_label, body) => {
      mockLoginLinkAutoLogin.mockRejectedValue(httpError(400, body));
      mockGetAccessToken.mockReturnValue('stored-access-token');
      seedHandoff('used123');

      const {container} = renderPage('/login-link');

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
      expect(mockBootstrapAuthSession).toHaveBeenCalledTimes(1);
      expect(container.querySelector('.magic-login-error')).toBeNull();
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(handoffToken()).toBeNull();
    });

    it('still goes to /account, not to the link destination, when the body carries one', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has already been used.', code: 'already_used', redirect_to: '/schedule'}),
      );
      mockGetAccessToken.mockReturnValue('stored-access-token');

      renderPage('/login-link?token=used123');

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
      expect(mockNavigate).toHaveBeenCalledTimes(1);
    });

    it('offers the email-code sign-in when no session is stored', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has already been used.', code: 'already_used'}),
      );
      seedHandoff('used123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.used);
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(handoffToken()).toBeNull();
    });

    it('treats unreadable storage as no stored session', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has already been used.', code: 'already_used'}),
      );
      mockGetAccessToken.mockImplementation(() => {
        throw new Error('storage denied');
      });

      const {container} = renderPage('/login-link?token=used123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.used);
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('falls back if continuing to /account throws', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has already been used.', code: 'already_used'}),
      );
      mockGetAccessToken.mockReturnValue('stored-access-token');
      mockNavigate.mockImplementationOnce(() => {
        throw new Error('router exploded');
      });

      const {container} = renderPage('/login-link?token=used123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.retryable);
    });
  });
});
