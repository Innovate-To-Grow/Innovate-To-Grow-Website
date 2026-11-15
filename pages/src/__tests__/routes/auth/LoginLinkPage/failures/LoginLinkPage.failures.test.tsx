import {AxiosError} from 'axios';
import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  MalformedLoginResponseError,
} from '@/features/auth/api/contracts/errors';
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

const NOT_SAVED = 'Your browser blocked saving your login session. Please log in manually.';

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

const networkError = () => new AxiosError('Network Error', AxiosError.ERR_NETWORK);

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

  describe('a retryable failure', () => {
    it('shows the fallback and a retry for a rate limit, and retries with the same token', async () => {
      mockLoginLinkAutoLogin
        .mockRejectedValueOnce(httpError(429, {detail: 'Request was throttled.'}))
        .mockResolvedValueOnce(LOGIN_RESPONSE);
      mockGetAccessToken.mockReturnValue('stored-access-token');
      seedHandoff('busy123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();
      expectFallback(container, NOTICE.retryable);
      expect(mockNavigate).not.toHaveBeenCalled();
      // The token has not been spent, so it stays available for a reload.
      expect(handoffToken()).toBe('busy123');

      fireEvent.click(screen.getByRole('button', {name: RETRY}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(2);
      expect(mockLoginLinkAutoLogin).toHaveBeenNthCalledWith(1, 'busy123');
      expect(mockLoginLinkAutoLogin).toHaveBeenNthCalledWith(2, 'busy123');
      expect(mockDispatchAuthStateChange).toHaveBeenCalledTimes(1);
      expect(handoffToken()).toBeNull();
    });

    it.each([
      ['429', httpError(429)],
      ['408', httpError(408)],
      ['500', httpError(500, {detail: 'Server error.'})],
      ['502 with an HTML body', httpError(502, '<html>Bad Gateway</html>')],
      ['503', httpError(503)],
      ['network error', networkError()],
      ['malformed 2xx body', new MalformedLoginResponseError()],
      ['unexpected non-HTTP error', new TypeError('boom')],
      // Only the typed error means "the browser blocked saving".
      ['plain Error that mentions persisting', new Error('Unable to persist the authentication session.')],
    ])('offers the fallback and a retry (%s)', async (_label, error) => {
      mockLoginLinkAutoLogin.mockRejectedValueOnce(error).mockResolvedValueOnce(LOGIN_RESPONSE);
      mockGetAccessToken.mockReturnValue('stored-access-token');
      seedHandoff('flaky123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();
      expectFallback(container, NOTICE.retryable);
      expect(screen.queryByText(NOT_SAVED)).toBeNull();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(handoffToken()).toBe('flaky123');

      fireEvent.click(screen.getByRole('button', {name: RETRY}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(mockLoginLinkAutoLogin).toHaveBeenNthCalledWith(2, 'flaky123');
      expect(handoffToken()).toBeNull();
    });

    it('lets a reloaded page try again from the retained handoff', async () => {
      mockLoginLinkAutoLogin
        .mockRejectedValueOnce(httpError(503))
        .mockResolvedValueOnce(LOGIN_RESPONSE);
      seedHandoff('reload123');

      const first = renderPage('/login-link');
      expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();
      first.unmount();

      // A reload re-mounts the page with only the sessionStorage handoff left.
      renderPage('/login-link');

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(mockLoginLinkAutoLogin).toHaveBeenNthCalledWith(2, 'reload123');
      expect(handoffToken()).toBeNull();
    });
  });
});
