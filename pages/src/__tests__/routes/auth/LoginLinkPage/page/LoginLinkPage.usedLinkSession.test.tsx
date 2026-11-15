import {AxiosError} from 'axios';
import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
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

const networkError = () => new AxiosError('Network Error', AxiosError.ERR_NETWORK);

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

    it('checks the stored session before deciding, and continues to /account when it is verified', async () => {
      mockGetAccessToken.mockReturnValue('stored-access-token');
      mockBootstrapAuthSession.mockResolvedValue({status: 'verified', session: STORED_SESSION});

      renderPage('/login-link?token=used123');

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
      expect(mockBootstrapAuthSession).toHaveBeenCalledTimes(1);
      expect(mockNavigate).toHaveBeenCalledTimes(1);
      expect(screen.queryByLabelText('Email address')).toBeNull();
    });

    it('continues to /account when the check could not reach a verdict (a transient failure)', async () => {
      mockGetAccessToken.mockReturnValue('stored-access-token');
      mockBootstrapAuthSession.mockResolvedValue({status: 'unverified', session: STORED_SESSION});

      renderPage('/login-link?token=used123');

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
      expect(mockNavigate).toHaveBeenCalledTimes(1);
      expect(screen.queryByLabelText('Email address')).toBeNull();
    });

    it('offers the code sign-in, aimed at the link destination, when the stored session is dead', async () => {
      // The check has already cleared the dead session and announced it; going
      // to /account would only leave the visitor anonymous there.
      const auth = buildAuth();
      mockUseAuth.mockReturnValue(auth);
      mockGetAccessToken.mockReturnValue('stale-access-token');
      mockBootstrapAuthSession.mockResolvedValue({status: 'anonymous', session: null});
      seedHandoff('used123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.used);
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(handoffToken()).toBeNull();

      fireEvent.change(screen.getByLabelText('Email address'), {target: {value: 'ada@example.com'}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
      await screen.findByRole('textbox', {name: '6-digit verification code'});
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(mockNavigate).not.toHaveBeenCalledWith('/account', {replace: true});
    });

    it('does not check anything, and offers the code sign-in, when no session is stored', async () => {
      mockGetAccessToken.mockReturnValue(null);

      const {container} = renderPage('/login-link?token=used123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expectFallback(container, NOTICE.used);
      expect(mockBootstrapAuthSession).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it.each([
      ['expired', httpError(400, {detail: 'This login link has expired.', code: 'expired'})],
      ['invalid', httpError(400, {detail: 'Invalid login link.', code: 'invalid_link'})],
      ['rate limited', httpError(429)],
      ['unreachable', networkError()],
    ])('never checks the stored session for a link that is %s', async (_label, error) => {
      mockLoginLinkAutoLogin.mockRejectedValue(error);
      mockGetAccessToken.mockReturnValue('stored-access-token');

      renderPage('/login-link?token=other123');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expect(mockBootstrapAuthSession).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });
});
