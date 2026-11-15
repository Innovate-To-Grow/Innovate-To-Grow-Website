import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  httpError,
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

describe('LoginLinkPage — the code sign-in inside the fallback', () => {
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

  describe('the code sign-in inside the fallback', () => {
    const openCodeStep = async (email = 'ada@example.com') => {
      fireEvent.change(await screen.findByLabelText('Email address'), {target: {value: email}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
      await screen.findByRole('textbox', {name: '6-digit verification code'});
    };

    const typeCodeAndVerify = (auth: ReturnType<typeof buildAuth>, response: unknown) => {
      auth.verifyLoginCode.mockResolvedValue(response);
      fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {
        target: {value: '123456'},
      });
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
    };

    it('never applies a destination from an invalid link', async () => {
      const auth = buildAuth();
      mockUseAuth.mockReturnValue(auth);
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'Invalid login link.', code: 'invalid_link', redirect_to: '/schedule'}),
      );

      renderPage('/login-link?token=bad123');
      await openCodeStep();
      typeCodeAndVerify(auth, {next_step: 'account', requires_profile_completion: false});

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
    });

    it('keeps the destination through a profile-completion detour', async () => {
      const auth = buildAuth();
      mockUseAuth.mockReturnValue(auth);
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'x', code: 'expired', redirect_to: '/schedule'}),
      );

      renderPage('/login-link?token=old123');
      await openCodeStep();
      typeCodeAndVerify(auth, {next_step: 'complete_profile', requires_profile_completion: true});

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fschedule', {replace: true});
      });
    });

    it('keeps the retry available on the email step of a retryable failure, but not on the code step', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(httpError(503));

      renderPage('/login-link?token=flaky123');
      expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();

      await openCodeStep();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();

      fireEvent.click(screen.getByRole('button', {name: 'Back'}));
      expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();
      expect(screen.getByLabelText('Email address')).toHaveValue('ada@example.com');
    });

    it('moves focus onto the code field when the code step opens', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(httpError(400, {detail: 'x', code: 'expired'}));

      renderPage('/login-link?token=old123');
      await openCodeStep();

      expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toHaveFocus();
    });
  });
});
