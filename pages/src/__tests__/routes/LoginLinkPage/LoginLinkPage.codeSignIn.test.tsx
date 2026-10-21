import {AxiosError, type AxiosResponse} from 'axios';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';

import {LoginLinkPage} from '@/routes/LoginLinkPage/LoginLinkPage';

const mockLoginLinkAutoLogin = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();
const mockGetAccessToken = vi.fn();
const mockBootstrapAuthSession = vi.fn();
const mockUseAuth = vi.fn();

vi.mock('@/features/auth/api/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/session')>()),
  loginLinkAutoLogin: (...args: unknown[]) => mockLoginLinkAutoLogin(...args),
  bootstrapAuthSession: () => mockBootstrapAuthSession(),
}));

vi.mock('@/features/auth/api/storage', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/storage')>()),
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

const INSTEAD = "Enter your email and we'll send you a 6-digit code to sign in instead.";
const NOTICE = {
  expired: 'This sign-in link has expired.',
  used: 'This sign-in link has already been used.',
  retryable: "We couldn't verify your sign-in link right now.",
  unusable: "This sign-in link can't be used.",
};

const RETRY = 'Try the link again';

const STORED_SESSION = {
  version: 1,
  generation: 'stored-generation',
  access: 'stored-access-token',
  refresh: 'stored-refresh-token',
  user: {member_uuid: 'stored-member', email: 'stored@example.com'},
  requires_profile_completion: false,
};

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

const httpError = (status: number, data?: unknown) =>
  new AxiosError(
    `Request failed with status code ${status}`,
    status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
    undefined,
    undefined,
    {status, statusText: '', headers: {}, config: {}, data} as AxiosResponse,
  );

// Stores the token the way main.tsx does before React mounts: captured into the
// sessionStorage handoff, with the URL scrubbed.
const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  captureAuthCallbackParams();
};

const handoffToken = () =>
  readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/login-link" element={<LoginLinkPage />} />
      </Routes>
    </MemoryRouter>,
  );

/**
 * A link that cannot be used is not an error: no alert, no error text, just an
 * informational notice and the inline email-code sign-in.
 */
const expectFallback = (container: HTMLElement, firstSentence: string) => {
  const notice = screen.getByRole('status');
  expect(notice).toHaveClass('auth-alert', 'info');
  expect(notice.textContent).toBe(`${firstSentence} ${INSTEAD}`);
  expect(screen.getByRole('heading', {name: 'Sign in to I2G', level: 1})).toBeInTheDocument();
  expect(screen.getByLabelText('Email address')).toHaveAttribute('type', 'email');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(container.querySelector('.magic-login-error')).toBeNull();
  expect(container.querySelector('.auth-alert.error')).toBeNull();
};

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

    describe('the retained handoff of a retryable failure', () => {
      it('is dropped when the code step opens, yet Back then Retry still uses the token held in memory', async () => {
        mockLoginLinkAutoLogin
          .mockRejectedValueOnce(httpError(503))
          .mockResolvedValueOnce(LOGIN_RESPONSE);
        seedHandoff('flaky123');

        renderPage('/login-link');
        expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();
        expect(handoffToken()).toBe('flaky123');

        await openCodeStep();
        expect(handoffToken()).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Back'}));
        fireEvent.click(await screen.findByRole('button', {name: RETRY}));

        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
        });
        expect(mockLoginLinkAutoLogin).toHaveBeenNthCalledWith(2, 'flaky123');
      });

      it('cannot be replayed by a bare /login-link visit after the code sign-in', async () => {
        const auth = buildAuth();
        mockUseAuth.mockReturnValue(auth);
        mockLoginLinkAutoLogin.mockRejectedValue(httpError(503));
        seedHandoff('flaky123');

        const first = renderPage('/login-link');
        await openCodeStep();
        typeCodeAndVerify(auth, {next_step: 'account', requires_profile_completion: false});
        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
        });
        expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(1);
        first.unmount();

        // Later, in the same tab: nothing is left to submit.
        const {container} = renderPage('/login-link');

        expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
        expectFallback(container, NOTICE.unusable);
        expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(1);
      });
    });
  });
});
