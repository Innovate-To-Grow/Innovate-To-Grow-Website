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
});
