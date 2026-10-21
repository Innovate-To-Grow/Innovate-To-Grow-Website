// Two regressions for emailed login links, both driven through the REAL auth
// client, storage, and page against a fake axios adapter.
//
// 1. A link that showed as unusable in a browser that already held a session.
//    The fake behaves like the backend did before its own fix: LoginLinkView ran
//    JWT authentication ahead of the view, so any expired bearer was answered
//    with 401 and the emailed token was never consumed.
//
// 2. A link that cannot be used must not be an error. The fake behaves like the
//    fixed backend and the page falls back to signing in with an emailed code
//    (the existing-accounts `login` flow), inline on /login-link, with the real
//    AuthProvider, so a stored session from another account is replaced rather
//    than stranding the visitor.
import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {authApi} from '@/features/auth/api/client';
import {captureAuthCallbackParams, readAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {getStoredSession, persistAuthSession} from '@/features/auth/api/storage';
import {AuthProvider} from '@/features/auth/components/AuthContext';
import {LoginLinkPage} from '@/routes/LoginLinkPage/LoginLinkPage';

const mockRequestLoginCode = vi.fn();

// The code request runs a proof-of-work challenge against three extra endpoints;
// that machinery has its own tests. Everything after it (verify, storage, the
// provider, the event) is real.
vi.mock('@/features/auth/api/flows', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/flows')>()),
  requestLoginCode: (...args: unknown[]) => mockRequestLoginCode(...args),
}));

const STALE_ACCESS = 'stale-access';

// Someone else's account, for a browser that signs in by code instead of by link.
const MEMBER_B = {member_uuid: 'member-b', email: 'b@example.com'};

const NEW_ACCOUNT = {
  message: 'Login successful.',
  access: 'new-access',
  refresh: 'new-refresh',
  user: {member_uuid: 'member-new', email: 'new@example.com'},
  requires_profile_completion: false,
  redirect_to: '/schedule',
};

interface RecordedRequest {
  url: string;
  authorization: unknown;
  body: unknown;
}

type Reply = {status: number; data: unknown};

let requests: RecordedRequest[];

const reply = (config: InternalAxiosRequestConfig, {status, data}: Reply) => {
  const response = {
    data,
    status,
    statusText: '',
    headers: {},
    config,
    request: {},
  } as AxiosResponse;
  if (status >= 200 && status < 300) return Promise.resolve(response);
  return Promise.reject(
    new AxiosError(
      `Request failed with status code ${status}`,
      status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
      config,
      {},
      response,
    ),
  );
};

const record = (config: InternalAxiosRequestConfig): RecordedRequest => {
  const request = {
    url: config.url ?? '',
    authorization: config.headers.get('Authorization') ?? null,
    body: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
  };
  requests.push(request);
  return request;
};

const seedStaleSession = () =>
  persistAuthSession({
    access: STALE_ACCESS,
    refresh: 'stale-refresh',
    user: {member_uuid: 'member-old', email: 'old@example.com'},
    requires_profile_completion: false,
  });

// What main.tsx does before React mounts: the token moves into the
// sessionStorage handoff and the URL is scrubbed.
const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  sessionStorage.clear();
  captureAuthCallbackParams();
};

const handoffToken = () =>
  readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

const requestsTo = (suffix: string) => requests.filter((request) => request.url.endsWith(suffix));
const refreshRequests = () => requestsTo('/authn/refresh/');
const loginLinkRequests = () => requestsTo('/mail/login-link/');

const useAdapter = (adapter: AxiosAdapter) => {
  // authApi carries its own copy of the defaults, and the refresh call goes
  // through the global instance, so both need the fake.
  authApi.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
};

describe('LoginLinkPage falling back to an emailed code — addresses, codes and failures', () => {
  const originalAuthAdapter = authApi.defaults.adapter;
  const originalAxiosAdapter = axios.defaults.adapter;

  const TOKENS = {
    expired: 'expired-token',
    used: 'used-token',
    unknown: 'unknown-token',
    flaky: 'flaky-token',
    html: 'html-token',
    ok: 'ok-token',
  };
  const GOOD_CODE = '123456';

  // What the backend puts in the 400 bodies of an expired or used link: the
  // link's own post-login destination (undefined = an older backend).
  let linkRedirect: unknown;
  // ...and what a buggy backend might add to an invalid link (it must be ignored).
  let invalidLinkRedirect: unknown;
  let flakyCalls: number;
  let codeReply: Reply;
  // Whether the stale session seeded by seedStaleSession() was revoked server-side.
  let staleSessionDead: boolean;
  // Whom the emailed code signs in (the link's owner is NEW_ACCOUNT).
  let codeAccount: Record<string, unknown>;

  // The login-code verify endpoint answers with the session and a next step but,
  // unlike the login link, no redirect_to: the page has to carry the link's own
  // destination through itself.
  const {redirect_to: _linkOnly, ...sessionFields} = NEW_ACCOUNT;
  void _linkOnly;
  const verifyResponse = {
    ...sessionFields,
    next_step: 'account',
    requires_profile_completion: false,
  };
  const MEMBER_B_ACCESS = 'b-access';
  const memberBResponse = {
    ...verifyResponse,
    access: MEMBER_B_ACCESS,
    refresh: 'b-refresh',
    user: MEMBER_B,
  };

  // The fixed backend: the exchange endpoints run no authentication at all, so
  // the stored bearer is irrelevant to them.
  const fixedBackend: AxiosAdapter = (config) => {
    const {url, authorization, body} = record(config);
    const token = (body as {token?: string} | undefined)?.token;
    const withRedirect = (redirect: unknown) => (redirect === undefined ? {} : {redirect_to: redirect});

    if (url.endsWith('/mail/login-link/')) {
      switch (token) {
        case TOKENS.expired:
          return reply(config, {
            status: 400,
            data: {detail: 'This login link has expired.', code: 'expired', ...withRedirect(linkRedirect)},
          });
        case TOKENS.used:
          return reply(config, {
            status: 400,
            data: {detail: 'This login link has already been used.', code: 'already_used', ...withRedirect(linkRedirect)},
          });
        case TOKENS.flaky:
          flakyCalls += 1;
          return flakyCalls === 1
            ? reply(config, {status: 503, data: '<html>Service Unavailable</html>'})
            : reply(config, {status: 200, data: NEW_ACCOUNT});
        case TOKENS.html:
          return reply(config, {status: 200, data: '<!doctype html><html></html>'});
        case TOKENS.ok:
          return reply(config, {status: 200, data: NEW_ACCOUNT});
        default:
          return reply(config, {
            status: 400,
            data: {detail: 'Invalid login link.', code: 'invalid_link', ...withRedirect(invalidLinkRedirect)},
          });
      }
    }

    if (url.endsWith('/authn/login/verify-code/')) {
      const code = (body as {code?: string} | undefined)?.code;
      return code === GOOD_CODE ? reply(config, {status: 200, data: codeAccount}) : reply(config, codeReply);
    }

    if (url.endsWith('/authn/session/')) {
      if (authorization === `Bearer ${STALE_ACCESS}` && !staleSessionDead) {
        return reply(config, {
          status: 200,
          data: {authenticated: true, user: {member_uuid: 'member-old', email: 'old@example.com'}},
        });
      }
      if (authorization === `Bearer ${NEW_ACCOUNT.access}`) {
        return reply(config, {status: 200, data: {authenticated: true, user: NEW_ACCOUNT.user}});
      }
      if (authorization === `Bearer ${MEMBER_B_ACCESS}`) {
        return reply(config, {status: 200, data: {authenticated: true, user: MEMBER_B}});
      }
      return reply(config, {status: 401, data: {detail: 'Authentication credentials were not provided.'}});
    }

    if (url.endsWith('/authn/refresh/')) return reply(config, {status: 401, data: {detail: 'Token is invalid'}});

    return reply(config, {status: 404, data: {detail: 'Not found.'}});
  };

  const renderApp = () =>
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/login-link']}>
          <Routes>
            <Route path="/login-link" element={<LoginLinkPage />} />
            <Route path="/login" element={<p>Login route</p>} />
            <Route path="/verify-email" element={<p>Verify-email route</p>} />
            <Route path="/schedule" element={<p>Schedule page</p>} />
            <Route path="/account" element={<p>Account page</p>} />
            <Route path="/complete-profile" element={<p>Complete-profile page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

  const openLink = async (token: string) => {
    seedHandoff(token);
    const view = renderApp();
    await screen.findByLabelText('Email address');
    return view;
  };

  const typeEmailAndSend = async (email = 'New@Example.com') => {
    fireEvent.change(screen.getByLabelText('Email address'), {target: {value: email}});
    fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
    await screen.findByRole('textbox', {name: '6-digit verification code'});
  };

  const typeCodeAndContinue = (code = GOOD_CODE) => {
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: code}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
  };

  beforeEach(() => {
    requests = [];
    flakyCalls = 0;
    linkRedirect = '/schedule';
    invalidLinkRedirect = undefined;
    codeReply = {status: 400, data: {detail: 'Invalid or expired code.'}};
    staleSessionDead = false;
    codeAccount = verifyResponse;
    mockRequestLoginCode.mockReset();
    mockRequestLoginCode.mockResolvedValue({
      message: 'If an eligible account exists, a verification code has been sent.',
    });
    localStorage.clear();
    sessionStorage.clear();
    useAdapter(fixedBackend);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    authApi.defaults.adapter = originalAuthAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  it('takes a mistyped address to the same code step, where nothing it could receive signs anyone in', async () => {
    // The login flow answers every address alike, so the page advances; a code
    // for an address without an account is simply rejected. Crucially, no
    // pending account is created and the stored session is left alone: the
    // unified email-auth endpoints are never called.
    seedStaleSession();
    await openLink(TOKENS.expired);
    codeReply = {status: 400, data: {detail: 'Verification code is invalid or has expired.'}};

    await typeEmailAndSend('typo@example.com');
    expect(screen.getByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
    typeCodeAndContinue('654321');

    expect(await screen.findByRole('alert')).toHaveTextContent('Verification code is invalid or has expired.');
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS, user: {member_uuid: 'member-old'}});
    expect(requestsTo('/authn/email-auth/request-code/')).toHaveLength(0);
    expect(requestsTo('/authn/email-auth/verify-code/')).toHaveLength(0);
  });

  it.each([
    ['an absolute URL', 'https://evil.example/phish'],
    ['a protocol-relative URL', '//evil.example'],
    ['a javascript: URL', 'javascript:alert(1)'],
    ['a backslash path', '/\\evil.example'],
    ['a non-string', {path: '/schedule'}],
    ['nothing (an older backend)', undefined],
  ])('ignores an unusable link destination (%s) and lands on /account', async (_label, redirect) => {
    linkRedirect = redirect;
    await openLink(TOKENS.expired);

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Account page')).toBeInTheDocument();
    expect(screen.queryByText('Schedule page')).toBeNull();
  });

  it('never applies a destination from an invalid link', async () => {
    invalidLinkRedirect = '/schedule';
    await openLink(TOKENS.unknown);
    expect(screen.getByRole('status')).toHaveTextContent("This sign-in link can't be used.");

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Account page')).toBeInTheDocument();
  });

  it('keeps the link destination through a profile-completion detour', async () => {
    await openLink(TOKENS.expired);
    // Answers the code exchange with an account that still has to finish its profile.
    const incomplete = {...verifyResponse, next_step: 'complete_profile', requires_profile_completion: true};
    const adapter: AxiosAdapter = (config) =>
      (config.url ?? '').endsWith('/authn/login/verify-code/')
        ? reply(config, {status: 200, data: incomplete})
        : fixedBackend(config);
    useAdapter(adapter);

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Complete-profile page')).toBeInTheDocument();
  });

  it('shows a wrong code as an error, keeps the stored session, and accepts the right code afterwards', async () => {
    seedStaleSession();
    await openLink(TOKENS.expired);
    await typeEmailAndSend();

    typeCodeAndContinue('000000');

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid or expired code.');
    expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toBeInTheDocument();
    expect(screen.queryByText('Schedule page')).toBeNull();
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});

    typeCodeAndContinue();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(getStoredSession()).toMatchObject({access: 'new-access'});
  });

  it('resends the code from the code step', async () => {
    await openLink(TOKENS.expired);
    await typeEmailAndSend();
    mockRequestLoginCode.mockClear();
    mockRequestLoginCode.mockResolvedValue({message: 'A new code is on its way.'});

    fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

    expect(await screen.findByText('A new code is on its way.')).toBeInTheDocument();
    expect(mockRequestLoginCode.mock.calls[0]).toEqual(['new@example.com']);
    expect(mockRequestLoginCode).toHaveBeenCalledTimes(1);

    // The resent code still signs in.
    typeCodeAndContinue();
    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
  });

  it('goes back from the code step to the email step without leaving the page', async () => {
    seedStaleSession();
    await openLink(TOKENS.expired);
    await typeEmailAndSend();

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(await screen.findByLabelText('Email address')).toHaveValue('New@Example.com');
    expect(screen.queryByText('Login route')).toBeNull();
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
  });

  describe('email validation', () => {
    it.each([
      ['an empty field', '', 'Please enter your email address.'],
      ['a name', 'new', 'Please enter a valid email address.'],
      ['a phone number', '2015550123', 'Please enter a valid email address.'],
    ])('rejects %s and sends nothing', async (_label, value, message) => {
      await openLink(TOKENS.expired);

      fireEvent.change(screen.getByLabelText('Email address'), {target: {value}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));

      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(mockRequestLoginCode).not.toHaveBeenCalled();
      expect(screen.queryByRole('textbox', {name: '6-digit verification code'})).toBeNull();
    });

    it('shows a failure to send the code and lets the visitor try again', async () => {
      await openLink(TOKENS.expired);
      mockRequestLoginCode.mockRejectedValueOnce(
        Object.assign(new Error('throttled'), {response: {status: 429, data: {detail: 'Too many requests. Try again later.'}}}),
      );

      fireEvent.change(screen.getByLabelText('Email address'), {target: {value: 'new@example.com'}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));

      expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests. Try again later.');
      expect(screen.getByLabelText('Email address')).toHaveValue('new@example.com');

      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
      expect(await screen.findByRole('textbox', {name: '6-digit verification code'})).toBeInTheDocument();
    });
  });

  describe('a retryable failure', () => {
    it('offers the fallback and a retry; the retry signs in through the link itself', async () => {
      seedStaleSession();
      await openLink(TOKENS.flaky);

      expect(screen.getByRole('status')).toHaveTextContent("We couldn't verify your sign-in link right now.");
      expect(screen.queryByRole('alert')).toBeNull();
      expect(handoffToken()).toBe(TOKENS.flaky);

      fireEvent.click(screen.getByRole('button', {name: 'Try the link again'}));

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(loginLinkRequests()).toHaveLength(2);
      expect(loginLinkRequests().every((request) => request.authorization === null)).toBe(true);
      expect(refreshRequests()).toHaveLength(0);
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
      expect(handoffToken()).toBeNull();
    });

    it('drops the retained link once the visitor signs in by code, so a bare /login-link cannot swap the account', async () => {
      // A 503 keeps the emailed token in sessionStorage for Retry or a reload.
      // The visitor then signs in as member B by code. Replaying the retained
      // token later would sign this browser in as the link's owner instead.
      codeAccount = memberBResponse;
      seedStaleSession();
      const first = await openLink(TOKENS.flaky);
      expect(handoffToken()).toBe(TOKENS.flaky);

      await typeEmailAndSend('b@example.com');
      expect(handoffToken()).toBeNull();
      typeCodeAndContinue();
      expect(await screen.findByText('Account page')).toBeInTheDocument();
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-b'}});
      first.unmount();

      // Later, in the same tab, a bare /login-link (no token in the URL).
      window.history.replaceState(null, '', '/login-link');
      renderApp();

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent("This sign-in link can't be used.");
      expect(screen.queryByRole('alert')).toBeNull();
      // Only the first, failed exchange ever left the browser.
      expect(loginLinkRequests()).toHaveLength(1);
      expect(flakyCalls).toBe(1);
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-b'}});
    });

    it('lets Back then Retry still use the token held in memory after the code step opened', async () => {
      seedStaleSession();
      await openLink(TOKENS.flaky);

      await typeEmailAndSend('b@example.com');
      expect(handoffToken()).toBeNull();
      fireEvent.click(screen.getByRole('button', {name: 'Back'}));
      fireEvent.click(await screen.findByRole('button', {name: 'Try the link again'}));

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(loginLinkRequests()).toHaveLength(2);
      expect(loginLinkRequests()[1]).toMatchObject({body: {token: TOKENS.flaky}});
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
    });

    it('treats a 2xx answer that is not a login as retryable, never as a blocked browser', async () => {
      seedStaleSession();
      const {container} = await openLink(TOKENS.html);

      expect(screen.getByRole('status')).toHaveTextContent("We couldn't verify your sign-in link right now.");
      expect(screen.getByRole('button', {name: 'Try the link again'})).toBeInTheDocument();
      expect(screen.queryByText(/blocked saving/i)).toBeNull();
      expect(container.querySelector('.magic-login-error')).toBeNull();
      expect(screen.queryByRole('alert')).toBeNull();
      // The token was not consumed, so it is kept for a retry or a reload.
      expect(handoffToken()).toBe(TOKENS.html);
      // Nothing malformed reached storage, and the stale session is untouched.
      expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
    });
  });

  describe('a browser that cannot store the session', () => {
    it('keeps the plain error, with no fallback, because a code sign-in could not persist either', async () => {
      seedStaleSession();
      seedHandoff(TOKENS.ok);
      const setItem = Storage.prototype.setItem;
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
        if (this === window.localStorage) {
          throw new DOMException('Storage is unavailable', 'QuotaExceededError');
        }
        return setItem.call(this, key, value);
      });

      const {container} = renderApp();

      expect(
        await screen.findByText('Your browser blocked saving your login session. Please log in manually.'),
      ).toBeInTheDocument();
      expect(container.querySelector('.magic-login-error')).not.toBeNull();
      expect(screen.getByRole('link', {name: 'Go to Login'})).toBeInTheDocument();
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(screen.queryByRole('button', {name: 'Try the link again'})).toBeNull();
      // The exchange happened exactly once and its token is gone.
      expect(loginLinkRequests()).toHaveLength(1);
      expect(handoffToken()).toBeNull();
      expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
    });
  });
});
