import {AxiosError} from 'axios';
import {act, cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  expectFallback,
  handoffToken,
  httpError,
  INSTEAD,
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
    it('can be retried again after another retryable failure', async () => {
      mockLoginLinkAutoLogin
        .mockRejectedValueOnce(httpError(429))
        .mockRejectedValueOnce(networkError())
        .mockResolvedValueOnce(LOGIN_RESPONSE);

      renderPage('/login-link?token=again123');

      fireEvent.click(await screen.findByRole('button', {name: RETRY}));
      fireEvent.click(await screen.findByRole('button', {name: RETRY}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(3);
    });

    it('turns a retried failure into a final one once the server answers definitively', async () => {
      mockLoginLinkAutoLogin
        .mockRejectedValueOnce(httpError(429))
        .mockRejectedValueOnce(httpError(400, {detail: 'This login link has expired.', code: 'expired'}));
      seedHandoff('late123');

      const {container} = renderPage('/login-link');

      fireEvent.click(await screen.findByRole('button', {name: RETRY}));

      await waitFor(() => {
        expect(screen.getByRole('status').textContent).toBe(`${NOTICE.expired} ${INSTEAD}`);
      });
      expectFallback(container, NOTICE.expired);
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(handoffToken()).toBeNull();
    });

    it('does not submit again while a retry is in flight', async () => {
      let resolveRetry!: (value: typeof LOGIN_RESPONSE) => void;
      mockLoginLinkAutoLogin
        .mockRejectedValueOnce(httpError(429))
        .mockReturnValueOnce(
          new Promise((resolve) => {
            resolveRetry = resolve;
          }),
        );

      renderPage('/login-link?token=slow123');

      const retry = await screen.findByRole('button', {name: RETRY});
      fireEvent.click(retry);
      fireEvent.click(retry);

      expect(screen.getByText('Signing you in...')).toBeInTheDocument();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(2);

      await act(async () => {
        resolveRetry(LOGIN_RESPONSE);
      });
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(2);
    });
  });
});
