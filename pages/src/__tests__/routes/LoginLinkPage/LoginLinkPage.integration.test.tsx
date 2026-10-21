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
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {authApi} from '@/features/auth/api/client';
import {captureAuthCallbackParams} from '@/features/auth/api/callbackParams';
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

const EMAILED_TOKEN = 'emailed-token';
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

const requestsTo = (suffix: string) => requests.filter((request) => request.url.endsWith(suffix));
const refreshRequests = () => requestsTo('/authn/refresh/');
const loginLinkRequests = () => requestsTo('/mail/login-link/');

const useAdapter = (adapter: AxiosAdapter) => {
  // authApi carries its own copy of the defaults, and the refresh call goes
  // through the global instance, so both need the fake.
  authApi.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
};

describe('LoginLinkPage against the pre-fix backend with a stale stored session', () => {
  const originalAuthAdapter = authApi.defaults.adapter;
  const originalAxiosAdapter = axios.defaults.adapter;

  let refreshReply: Reply;
  let loginLinkConsumed: boolean;

  const oldBackend: AxiosAdapter = (config) => {
    const {url, authorization, body} = record(config);

    if (url.endsWith('/authn/refresh/')) return reply(config, refreshReply);

    if (url.endsWith('/mail/login-link/')) {
      // DRF authenticates before the view body runs: an expired bearer is a 401
      // and the emailed token is left unused.
      if (authorization === `Bearer ${STALE_ACCESS}`) {
        return reply(config, {
          status: 401,
          data: {detail: 'Given token not valid for any token type', code: 'token_not_valid'},
        });
      }
      if ((body as {token?: string})?.token !== EMAILED_TOKEN || loginLinkConsumed) {
        return reply(config, {status: 400, data: {detail: 'Invalid login link.'}});
      }
      loginLinkConsumed = true;
      return reply(config, {status: 200, data: NEW_ACCOUNT});
    }

    if (url.endsWith('/probe-401/')) return reply(config, {status: 401, data: {detail: 'Unauthorized.'}});

    return reply(config, {status: 404, data: {detail: 'Not found.'}});
  };

  // No AuthProvider here: these cases never reach the fallback's form, and a
  // provider would run its own session check with the stale bearer.
  const renderLoginLink = () =>
    render(
      <MemoryRouter initialEntries={['/login-link']}>
        <Routes>
          <Route path="/login-link" element={<LoginLinkPage />} />
          <Route path="/schedule" element={<p>Schedule page</p>} />
          <Route path="/account" element={<p>Account page</p>} />
        </Routes>
      </MemoryRouter>,
    );

  beforeEach(() => {
    requests = [];
    loginLinkConsumed = false;
    refreshReply = {status: 401, data: {detail: 'Token is invalid or expired', code: 'token_not_valid'}};
    localStorage.clear();
    sessionStorage.clear();
    useAdapter(oldBackend);
    seedHandoff(EMAILED_TOKEN);
    seedStaleSession();
  });

  afterEach(() => {
    cleanup();
    authApi.defaults.adapter = originalAuthAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  it('proves the emulated backend still fails an exchange that carries the stale bearer', async () => {
    // Guards the regression tests below against a fake that is too forgiving:
    // without the opt-out, the exchange dies exactly as reported.
    await expect(
      authApi.post('/mail/login-link/', {token: EMAILED_TOKEN}),
    ).rejects.toMatchObject({response: {status: 401}});

    expect(loginLinkRequests()[0].authorization).toBe(`Bearer ${STALE_ACCESS}`);
    expect(refreshRequests()).toHaveLength(1);
    expect(loginLinkConsumed).toBe(false);
    // The refresh was rejected definitively, so the client destroyed the session.
    expect(getStoredSession()).toBeNull();
  });

  it('keeps the stored session when an opted-out request is answered with 401', async () => {
    await expect(
      authApi.post('/probe-401/', {}, {skipAuth: true}),
    ).rejects.toMatchObject({response: {status: 401}});

    expect(requests[0].authorization).toBeNull();
    expect(refreshRequests()).toHaveLength(0);
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
  });

  it.each([
    ['the refresh token is rejected (401)', {status: 401, data: {detail: 'Token is blacklisted'}}],
    ['the refresh token is rejected (400)', {status: 400, data: {detail: 'Invalid token'}}],
    ['the member was deleted and refresh answers 500', {status: 500, data: '<h1>Server Error (500)</h1>'}],
  ])('signs the new account in and lands on redirect_to when %s', async (_label, refresh) => {
    refreshReply = refresh;

    renderLoginLink();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();

    // One anonymous exchange: no bearer, no refresh, token consumed exactly once.
    expect(loginLinkRequests()).toHaveLength(1);
    expect(loginLinkRequests()[0]).toMatchObject({
      authorization: null,
      body: {token: EMAILED_TOKEN},
    });
    expect(refreshRequests()).toHaveLength(0);
    expect(loginLinkConsumed).toBe(true);

    // The new account replaced the stale one in the single session slot.
    expect(getStoredSession()).toMatchObject({
      access: 'new-access',
      refresh: 'new-refresh',
      user: {member_uuid: 'member-new', email: 'new@example.com'},
    });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByLabelText('Email address')).toBeNull();
  });

  it('shows the sign-in fallback, and is not sent to /account as the stale account, when the link itself is bad', async () => {
    seedHandoff('some-other-token');

    const {container} = renderLoginLink();

    expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent("This sign-in link can't be used.");
    expect(screen.queryByRole('alert')).toBeNull();
    expect(container.querySelector('.magic-login-error')).toBeNull();
    expect(screen.queryByText('Account page')).toBeNull();
    expect(refreshRequests()).toHaveLength(0);
    // An anonymous exchange neither uses nor destroys the stored session.
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS, user: {member_uuid: 'member-old'}});
    await waitFor(() => expect(loginLinkRequests()).toHaveLength(1));
  });
});

describe('LoginLinkPage falling back to an emailed code against the fixed backend', () => {
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

  let authEvents: number;
  const countAuthEvent = () => {
    authEvents += 1;
  };

  beforeEach(() => {
    requests = [];
    flakyCalls = 0;
    linkRedirect = '/schedule';
    invalidLinkRedirect = undefined;
    codeReply = {status: 400, data: {detail: 'Invalid or expired code.'}};
    staleSessionDead = false;
    codeAccount = verifyResponse;
    authEvents = 0;
    mockRequestLoginCode.mockReset();
    mockRequestLoginCode.mockResolvedValue({
      message: 'If an eligible account exists, a verification code has been sent.',
    });
    localStorage.clear();
    sessionStorage.clear();
    useAdapter(fixedBackend);
    window.addEventListener('i2g-auth-state-change', countAuthEvent);
  });

  afterEach(() => {
    cleanup();
    window.removeEventListener('i2g-auth-state-change', countAuthEvent);
    vi.restoreAllMocks();
    authApi.defaults.adapter = originalAuthAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  it.each([
    // A stored session is what makes "already used" continue to /account (the
    // deliberate one-time-link-clicked-twice case), so that link is exercised
    // without one. Every other failure must ignore the stored session.
    ['an expired link, with a stored session', TOKENS.expired, 'This sign-in link has expired.', true],
    ['an expired link, without one', TOKENS.expired, 'This sign-in link has expired.', false],
    ['a used link, without a stored session', TOKENS.used, 'This sign-in link has already been used.', false],
  ])(
    'signs in with the code and lands on the link destination (%s)',
    async (_label, token, sentence, hasStoredSession) => {
      if (hasStoredSession) seedStaleSession();

      const {container} = await openLink(token);

      // Not an error, and not the stale account's /account either.
      expect(screen.getByRole('status').textContent).toBe(
        `${sentence} Enter your email and we'll send you a 6-digit code to sign in instead.`,
      );
      expect(screen.queryByRole('alert')).toBeNull();
      expect(container.querySelector('.magic-login-error')).toBeNull();
      expect(screen.queryByText('Account page')).toBeNull();
      await waitFor(() => expect(screen.getByLabelText('Email address')).toHaveFocus());
      // The anonymous exchange neither used nor destroyed any stored session.
      expect(loginLinkRequests()).toHaveLength(1);
      expect(loginLinkRequests()[0]).toMatchObject({authorization: null, body: {token}});
      expect(refreshRequests()).toHaveLength(0);
      if (hasStoredSession) {
        expect(getStoredSession()).toMatchObject({access: STALE_ACCESS, user: {member_uuid: 'member-old'}});
      } else {
        expect(getStoredSession()).toBeNull();
      }

      await typeEmailAndSend();

      // Inline: no hop to a route that redirects a signed-in browser away.
      expect(mockRequestLoginCode.mock.calls[0]).toEqual(['new@example.com']);
      expect(mockRequestLoginCode).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
      expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toHaveFocus();
      expect(screen.getByText('new@example.com')).toBeInTheDocument();
      expect(screen.queryByText('Login route')).toBeNull();
      expect(screen.queryByText('Verify-email route')).toBeNull();

      const eventsBefore = authEvents;
      typeCodeAndContinue();

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(screen.queryByText('Account page')).toBeNull();

      // The code exchange is anonymous too, and carries exactly what was typed.
      const verifies = requestsTo('/authn/login/verify-code/');
      expect(verifies).toHaveLength(1);
      expect(verifies[0]).toMatchObject({
        authorization: null,
        body: {email: 'new@example.com', code: GOOD_CODE},
      });
      expect(refreshRequests()).toHaveLength(0);

      // Account B replaced account A (if any) in the single session slot.
      expect(getStoredSession()).toMatchObject({
        access: 'new-access',
        refresh: 'new-refresh',
        user: {member_uuid: 'member-new', email: 'new@example.com'},
      });
      expect(localStorage.getItem('i2g_auth_session')).not.toContain(STALE_ACCESS);
      // Every root learns about it.
      expect(authEvents).toBeGreaterThan(eventsBefore);
      // The unified flow (which would create an account for an unknown address)
      // was never used.
      expect(requestsTo('/authn/email-auth/verify-code/')).toHaveLength(0);
    },
  );

  it('sends a used link with a live stored session on to /account, without the fallback', async () => {
    seedStaleSession();
    seedHandoff(TOKENS.used);

    renderApp();

    expect(await screen.findByText('Account page')).toBeInTheDocument();
    expect(screen.queryByLabelText('Email address')).toBeNull();
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
  });

  it('offers the code sign-in for a used link whose stored session is dead, and lands on the link destination', async () => {
    // The provider's own check would clear this session as soon as /account
    // opened, leaving the visitor anonymous there and without the link's
    // destination. The page asks first, through the same shared check.
    staleSessionDead = true;
    seedStaleSession();
    seedHandoff(TOKENS.used);

    const {container} = renderApp();

    expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('This sign-in link has already been used.');
    expect(container.querySelector('.magic-login-error')).toBeNull();
    expect(screen.queryByText('Account page')).toBeNull();
    // The dead session is gone, and was checked once for both the page and the provider.
    expect(getStoredSession()).toBeNull();
    expect(requestsTo('/authn/session/')).toHaveLength(1);

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(screen.queryByText('Account page')).toBeNull();
    expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
  });

  it('offers the same fallback, and signs in, with no stored session', async () => {
    await openLink(TOKENS.expired);

    await typeEmailAndSend('new@example.com');
    typeCodeAndContinue();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
  });
});
