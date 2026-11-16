import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  httpError,
  renderPage,
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

    it.each([
      ['expired', {detail: 'This login link has expired.', code: 'expired', redirect_to: '/schedule'}],
      ['already used', {detail: 'This login link has already been used.', code: 'already_used', redirect_to: '/schedule'}],
    ])('lands where the %s link pointed, and stays on /login-link until then', async (_label, body) => {
      const auth = buildAuth();
      mockUseAuth.mockReturnValue(auth);
      mockLoginLinkAutoLogin.mockRejectedValue(httpError(400, body));

      renderPage('/login-link?token=old123');
      await openCodeStep();

      expect(auth.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
      // Inline: no hop to /login or /verify-email, which redirect a signed-in browser.
      expect(mockNavigate).not.toHaveBeenCalled();

      typeCodeAndVerify(auth, {next_step: 'account', requires_profile_completion: false});

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
      });
      expect(auth.verifyLoginCode).toHaveBeenCalledWith('ada@example.com', '123456');
      // Only the existing-accounts flow: the unified one would create an account
      // for a mistyped address.
      expect(auth.requestEmailAuthCode).not.toHaveBeenCalled();
      expect(auth.verifyEmailAuthCode).not.toHaveBeenCalled();
    });

    it.each([
      ['an absolute URL', 'https://evil.example/x'],
      ['a protocol-relative URL', '//evil.example'],
      ['a javascript: URL', 'javascript:alert(1)'],
      ['a backslash path', '/\\evil.example'],
      ['a non-string', 7],
    ])('ignores an unsafe link destination (%s) and lands on /account', async (_label, redirectTo) => {
      const auth = buildAuth();
      mockUseAuth.mockReturnValue(auth);
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has expired.', code: 'expired', redirect_to: redirectTo}),
      );

      renderPage('/login-link?token=old123');
      await openCodeStep();
      typeCodeAndVerify(auth, {next_step: 'account', requires_profile_completion: false});

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
    });

    it('lands on /account when an older backend sends no link destination', async () => {
      const auth = buildAuth();
      mockUseAuth.mockReturnValue(auth);
      mockLoginLinkAutoLogin.mockRejectedValue(
        httpError(400, {detail: 'This login link has expired.'}),
      );

      renderPage('/login-link?token=old123');
      await openCodeStep();
      typeCodeAndVerify(auth, {next_step: 'account', requires_profile_completion: false});

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
    });
  });
});
