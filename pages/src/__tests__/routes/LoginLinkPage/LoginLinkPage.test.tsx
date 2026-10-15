import {AxiosError, type AxiosResponse} from 'axios';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';
import {
  MalformedLoginResponseError,
  SessionNotSavedError,
} from '@/features/auth/api/errors';
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
const NOT_SAVED = 'Your browser blocked saving your login session. Please log in manually.';
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

const networkError = () => new AxiosError('Network Error', AxiosError.ERR_NETWORK);

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

  it('navigates to the API-provided redirect when it is safe', async () => {
    mockLoginLinkAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: '/schedule',
    });

    renderPage('/login-link?token=abc123');

    await waitFor(() => {
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('abc123');
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
  });

  it('falls back to /account when the API redirect is unsafe', async () => {
    mockLoginLinkAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: 'https://evil.example',
    });

    renderPage('/login-link?token=unsafe123');

    await waitFor(() => {
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('unsafe123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('prefers complete-profile when the API says the account is incomplete', async () => {
    mockLoginLinkAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    });

    renderPage('/login-link?token=incomplete123');

    await waitFor(() => {
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('incomplete123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fschedule', {replace: true});
  });

  it('shows the sign-in fallback, not an error, when no token is provided', () => {
    const {container} = renderPage('/login-link');

    expectFallback(container, NOTICE.unusable);
    expect(screen.queryByText('No login token provided.')).toBeNull();
    expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
    expect(mockLoginLinkAutoLogin).not.toHaveBeenCalled();
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

  describe('a page that unmounts mid-exchange', () => {
    it('does not navigate after a late success, but still drops the spent token', async () => {
      let resolveExchange!: (value: typeof LOGIN_RESPONSE) => void;
      mockLoginLinkAutoLogin.mockReturnValue(
        new Promise((resolve) => {
          resolveExchange = resolve;
        }),
      );
      seedHandoff('late123');

      const view = renderPage('/login-link');
      await waitFor(() => {
        expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('late123');
      });
      view.unmount();
      await act(async () => {
        resolveExchange(LOGIN_RESPONSE);
      });

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
      expect(handoffToken()).toBeNull();
    });
  });

  describe('a step after the exchange that throws', () => {
    it.each([
      ['navigate', () => mockNavigate.mockImplementationOnce(() => {
        throw new Error('router exploded');
      })],
      ['the auth-state event', () => mockDispatchAuthStateChange.mockImplementationOnce(() => {
        throw new Error('listener exploded');
      })],
    ])('never leaves the page on "Signing you in..." when %s throws', async (_label, arrange) => {
      arrange();
      mockLoginLinkAutoLogin.mockResolvedValue(LOGIN_RESPONSE);
      seedHandoff('boom123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expect(screen.queryByText('Signing you in...')).toBeNull();
      expectFallback(container, NOTICE.retryable);
      // The exchange itself succeeded, so its token is spent and not retained.
      expect(handoffToken()).toBeNull();
    });

    it('runs nothing after the exchange once the page has unmounted, even if a step would throw', async () => {
      let resolveExchange!: (value: typeof LOGIN_RESPONSE) => void;
      mockLoginLinkAutoLogin.mockReturnValue(
        new Promise((resolve) => {
          resolveExchange = resolve;
        }),
      );
      // Would throw if reached: the page must return before dispatching at all.
      mockDispatchAuthStateChange.mockImplementation(() => {
        throw new Error('listener exploded');
      });
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

      const view = renderPage('/login-link?token=gone123');
      await waitFor(() => {
        expect(mockLoginLinkAutoLogin).toHaveBeenCalled();
      });
      view.unmount();
      await act(async () => {
        resolveExchange(LOGIN_RESPONSE);
      });

      expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(errorSpy).not.toHaveBeenCalled();
      errorSpy.mockRestore();
    });
  });

  describe('a session that could not be saved', () => {
    it('explains the blocked storage, keeps the plain error, and offers no fallback or retry', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(new SessionNotSavedError());
      // A stale session from another account must not hide the failure.
      mockGetAccessToken.mockReturnValue('stale-access-token');
      seedHandoff('spent123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByText(NOT_SAVED)).toBeInTheDocument();
      expect(container.querySelector('.magic-login-error')).toHaveTextContent(NOT_SAVED);
      expect(screen.getByRole('link', {name: 'Go to Login'})).toHaveAttribute('href', '/login');
      // The code sign-in could not persist a session either.
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(screen.queryByRole('status')).toBeNull();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
      // The token was consumed by the server, so nothing is worth keeping.
      expect(handoffToken()).toBeNull();
    });
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
