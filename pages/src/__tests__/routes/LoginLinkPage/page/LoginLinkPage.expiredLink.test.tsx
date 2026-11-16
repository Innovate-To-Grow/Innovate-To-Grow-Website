import {cleanup, screen} from '@testing-library/react';
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

  describe('an expired link', () => {
    it.each([
      ['machine-readable code', {detail: 'Link lapsed.', code: 'expired'}],
      ['detail text from an older backend', {detail: 'This login link has expired.'}],
    ])('shows the fallback, not an error (%s)', async (_label, body) => {
      mockLoginLinkAutoLogin.mockRejectedValue(httpError(400, body));
      seedHandoff('old123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.expired);
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(screen.queryByRole('link', {name: 'Go to Login'})).toBeNull();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(handoffToken()).toBeNull();
    });

    it('shows the fallback, and does not continue to /account, on behalf of a stored session', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has expired.', code: 'expired'}),
      );
      mockGetAccessToken.mockReturnValue('live-access-token');

      const {container} = renderPage('/login-link?token=old123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.expired);
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  describe('a link that cannot be used', () => {
    it.each([
      ['invalid_link code', httpError(400, {detail: 'Invalid login link.', code: 'invalid_link'})],
      ['token_required code', httpError(400, {detail: 'Token is required.', code: 'token_required'})],
      ['older backend detail only', httpError(400, {detail: 'Invalid login link.'})],
      ['400 without a body', httpError(400)],
      ['400 with a non-JSON body', httpError(400, '<html>Bad Request</html>')],
      ['401', httpError(401, {detail: 'Given token not valid for any token type'})],
      ['403', httpError(403, {detail: 'Forbidden.'})],
      ['404', httpError(404, '<h1>Not Found</h1>')],
      // Only a 400 says why the link failed; a 401 never means used or expired.
      ['401 whose detail mentions expiry', httpError(401, {detail: 'Token is expired', code: 'token_not_valid'})],
      ['401 that claims the link was used', httpError(401, {detail: 'This login link has already been used.', code: 'already_used'})],
      // The code decides, whatever the wording says.
      ['invalid_link whose detail mentions expiry', httpError(400, {detail: 'Invalid or expired login link.', code: 'invalid_link'})],
    ])('shows the fallback and never continues to /account (%s)', async (_label, error) => {
      mockLoginLinkAutoLogin.mockRejectedValue(error);
      mockGetAccessToken.mockReturnValue('stored-access-token');
      seedHandoff('bad123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.unusable);
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(handoffToken()).toBeNull();
    });

    it('shows the fallback with no stored session', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(httpError(400, {detail: 'Invalid login link.'}));

      const {container} = renderPage('/login-link?token=dead123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.unusable);
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });
});
