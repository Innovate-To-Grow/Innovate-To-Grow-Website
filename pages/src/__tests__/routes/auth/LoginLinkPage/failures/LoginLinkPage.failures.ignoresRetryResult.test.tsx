import {act, cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  httpError,
  renderPage,
  RETRY,
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

  describe('a retryable failure', () => {
    it('ignores a retry result that arrives after the page unmounted', async () => {
      let rejectRetry!: (reason: unknown) => void;
      mockLoginLinkAutoLogin
        .mockRejectedValueOnce(httpError(429))
        .mockReturnValueOnce(
          new Promise((_resolve, reject) => {
            rejectRetry = reject;
          }),
        );
      mockGetAccessToken.mockReturnValue('stored-access-token');
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

      const view = renderPage('/login-link?token=gone123');
      fireEvent.click(await screen.findByRole('button', {name: RETRY}));
      view.unmount();
      await act(async () => {
        rejectRetry(httpError(400, {detail: 'This login link has already been used.', code: 'already_used'}));
      });

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(errorSpy).not.toHaveBeenCalled();
      errorSpy.mockRestore();
    });

    it('lets the retry recover a page whose post-success step threw', async () => {
      // The session was stored and the token spent, so the retry is answered
      // "already used", which continues to /account for a stored session.
      mockLoginLinkAutoLogin
        .mockResolvedValueOnce(LOGIN_RESPONSE)
        .mockRejectedValueOnce(
          httpError(400, {detail: 'This login link has already been used.', code: 'already_used'}),
        );
      mockNavigate.mockImplementationOnce(() => {
        throw new Error('router exploded');
      });
      mockGetAccessToken.mockReturnValue('stored-access-token');

      renderPage('/login-link?token=spent123');

      fireEvent.click(await screen.findByRole('button', {name: RETRY}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenLastCalledWith('/account', {replace: true});
      });
    });
  });
});
