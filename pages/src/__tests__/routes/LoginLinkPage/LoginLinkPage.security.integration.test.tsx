// Only the server's verdict on an emailed token may sign anyone in. Nothing the
// visitor controls (the URL, the sessionStorage handoff, a session stored in
// localStorage) authorizes a sign-in, a session, or a protected destination on
// its own. Driven through the REAL auth client, storage, callback handoff, page
// and providers against a fake axios adapter that answers like LoginLinkView.
import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {authApi} from '@/features/auth/api/client';
import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';
import {getStoredSession, persistAuthSession} from '@/features/auth/api/storage';
import {AuthProvider, useAuth} from '@/features/auth/components/AuthContext';
import {LoginLinkPage} from '@/routes/LoginLinkPage/LoginLinkPage';

const VALID_TOKEN = 'valid-emailed-token';
const HANDOFF_KEY = 'i2g_callback_params:login-link';
const UNUSABLE = "This sign-in link can't be used.";

const NEW_ACCOUNT = {
  message: 'Login successful.',
  access: 'new-access',
  refresh: 'new-refresh',
  user: {member_uuid: 'member-new', email: 'new@example.com'},
  requires_profile_completion: false,
};

interface RecordedRequest {
  url: string;
  authorization: unknown;
  body: unknown;
}

type Reply = {status: number; data: unknown};

let requests: RecordedRequest[];
let linkSpent: boolean;
let successRedirect: unknown;

const reply = (config: InternalAxiosRequestConfig, {status, data}: Reply) => {
  const response = {data, status, statusText: '', headers: {}, config, request: {}} as AxiosResponse;
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

// LoginLinkView: the token alone decides, matched exactly and spent once; no
// header, cookie or stored session takes part.
const backend: AxiosAdapter = (config) => {
  const {url, authorization, body} = record(config);

  if (url.endsWith('/mail/login-link/')) {
    const token = (body as {token?: unknown} | undefined)?.token;
    if (typeof token !== 'string' || !token) {
      return reply(config, {status: 400, data: {detail: 'Token is required.', code: 'token_required'}});
    }
    if (token !== VALID_TOKEN) {
      return reply(config, {status: 400, data: {detail: 'Invalid login link.', code: 'invalid_link'}});
    }
    if (linkSpent) {
      return reply(config, {
        status: 400,
        data: {detail: 'This login link has already been used.', code: 'already_used', redirect_to: '/schedule'},
      });
    }
    linkSpent = true;
    return reply(config, {status: 200, data: {...NEW_ACCOUNT, redirect_to: successRedirect}});
  }

  if (url.endsWith('/authn/session/')) {
    if (authorization === `Bearer ${NEW_ACCOUNT.access}`) {
      return reply(config, {status: 200, data: {authenticated: true, user: NEW_ACCOUNT.user}});
    }
    return reply(config, {status: 401, data: {detail: 'Given token not valid for any token type', code: 'token_not_valid'}});
  }

  if (url.endsWith('/authn/refresh/')) {
    return reply(config, {status: 401, data: {detail: 'Token is invalid or expired', code: 'token_not_valid'}});
  }

  return reply(config, {status: 404, data: {detail: 'Not found.'}});
};

const loginLinkRequests = () => requests.filter((request) => request.url.endsWith('/mail/login-link/'));

// What main.tsx does before React mounts: the token moves into the
// sessionStorage handoff and the URL is scrubbed.
const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  captureAuthCallbackParams();
};

const handoffToken = () => readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

// A session a visitor wrote into localStorage by hand: well-formed, never issued.
const seedForgedSession = () =>
  persistAuthSession({
    access: 'forged-access',
    refresh: 'forged-refresh',
    user: {member_uuid: 'member-forged', email: 'forged@example.com', is_staff: true},
    requires_profile_completion: false,
  });

const appRoutes = (entry: string) => (
  <MemoryRouter initialEntries={[entry]}>
    <Routes>
      <Route path="/login-link" element={<LoginLinkPage />} />
      <Route path="/schedule" element={<p>Schedule page</p>} />
      <Route path="/account" element={<p>Account page</p>} />
      <Route path="/admin" element={<p>Admin page</p>} />
    </Routes>
  </MemoryRouter>
);

// The page alone: no provider runs its own session check, so every request and
// every auth event below comes from the page.
const renderPage = (entry = '/login-link') => render(appRoutes(entry));

function RootProbe({name}: {name: string}) {
  const {isAuthenticated, user} = useAuth();
  return <p>{`${name}: ${isAuthenticated && user ? user.email : 'signed out'}`}</p>;
}

// The three independent React roots of index.html, each with its own provider,
// kept in step only by the i2g-auth-state-change event.
const renderThreeRoots = (entry = '/login-link') => {
  render(<AuthProvider>{appRoutes(entry)}</AuthProvider>);
  render(<AuthProvider><RootProbe name="menu-root" /></AuthProvider>);
  render(<AuthProvider><RootProbe name="footer-root" /></AuthProvider>);
};

const expectUnusableFallback = async () => {
  expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent(UNUSABLE);
  expect(screen.queryByText('Schedule page')).toBeNull();
  expect(screen.queryByText('Account page')).toBeNull();
  expect(screen.queryByText('Admin page')).toBeNull();
};

describe('LoginLinkPage — only the server verdict on the token signs anyone in', () => {
  const originalAuthAdapter = authApi.defaults.adapter;
  const originalAxiosAdapter = axios.defaults.adapter;

  // The stored session at the moment each auth event is announced.
  let sessionsAtAuthEvents: (string | null)[];
  const recordAuthEvent = () => {
    sessionsAtAuthEvents.push(getStoredSession()?.access ?? null);
  };

  beforeEach(() => {
    requests = [];
    linkSpent = false;
    successRedirect = '/schedule';
    sessionsAtAuthEvents = [];
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
    authApi.defaults.adapter = backend;
    axios.defaults.adapter = backend;
    window.addEventListener('i2g-auth-state-change', recordAuthEvent);
  });

  afterEach(() => {
    cleanup();
    window.removeEventListener('i2g-auth-state-change', recordAuthEvent);
    authApi.defaults.adapter = originalAuthAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  describe('a link that carries no token', () => {
    it.each([
      ['a bare /login-link', () => undefined, '/login-link'],
      ['an empty token in the query', () => undefined, '/login-link?token='],
      ['an empty token captured from the fragment', () => seedHandoff(''), '/login-link'],
    ])('asks nothing, signs no one in, and leaves a stored session alone (%s)', async (_label, seed, entry) => {
      seed();
      seedForgedSession();

      renderPage(entry);

      await expectUnusableFallback();
      // A session in localStorage neither stands in for a token nor is touched.
      expect(requests).toHaveLength(0);
      expect(getStoredSession()).toMatchObject({access: 'forged-access', user: {member_uuid: 'member-forged'}});
      expect(sessionsAtAuthEvents).toEqual([]);
    });
  });

  describe('a tampered sessionStorage handoff', () => {
    it.each([
      ['a token that is not a string', JSON.stringify({capturedAt: Date.now(), params: {token: 12345}})],
      ['session fields instead of a token', JSON.stringify({
        capturedAt: Date.now(),
        params: {access: 'forged-access', refresh: 'forged-refresh', user: '{"is_staff":true}'},
      })],
      ['the real token, captured longer ago than the handoff lives', JSON.stringify({
        capturedAt: Date.now() - 16 * 60 * 1000,
        params: {token: VALID_TOKEN},
      })],
      ['unreadable JSON', '{"capturedAt":'],
    ])('is never sent and never becomes a session (%s)', async (_label, stored) => {
      sessionStorage.setItem(HANDOFF_KEY, stored);

      renderPage();

      await expectUnusableFallback();
      expect(requests).toHaveLength(0);
      expect(getStoredSession()).toBeNull();
      expect(sessionsAtAuthEvents).toEqual([]);
      expect(linkSpent).toBe(false);
    });
  });

  describe('a forged or altered token', () => {
    it.each([
      ['an unknown token', 'guessed-token'],
      ['the real token with its last character changed', `${VALID_TOKEN.slice(0, -1)}X`],
      ['the real token with characters appended', `${VALID_TOKEN}0`],
      ['the real token in another case', VALID_TOKEN.toUpperCase()],
    ])('is only ever judged by the server, and its rejection stands (%s)', async (_label, token) => {
      seedForgedSession();
      seedHandoff(token);

      renderPage();

      await expectUnusableFallback();
      // Sent once, as typed, and anonymously: the stored session plays no part.
      expect(loginLinkRequests()).toEqual([
        {url: expect.stringMatching(/\/mail\/login-link\/$/), authorization: null, body: {token}},
      ]);
      expect(requests).toHaveLength(1);
      // Neither a new session nor a hop to /account on the stored one's behalf.
      expect(getStoredSession()).toMatchObject({access: 'forged-access'});
      expect(sessionsAtAuthEvents).toEqual([]);
      // The rejection is final: the handoff is dropped so no reload replays it.
      expect(handoffToken()).toBeNull();
    });
  });

  it('does not continue to /account on a forged stored session when the link was already used', async () => {
    // The one place a stored session matters: a spent link continues to
    // /account only once the server has verified that session.
    linkSpent = true;
    seedForgedSession();
    seedHandoff(VALID_TOKEN);

    renderPage();

    expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('This sign-in link has already been used.');
    expect(screen.queryByText('Account page')).toBeNull();
    expect(requests.map((request) => request.url)).toEqual([
      expect.stringMatching(/\/mail\/login-link\/$/),
      expect.stringMatching(/\/authn\/session\/$/),
      expect.stringMatching(/\/authn\/refresh\/$/),
    ]);
    expect(requests[1].authorization).toBe('Bearer forged-access');
    // The server refused the session, so it was dropped and announced as gone.
    expect(getStoredSession()).toBeNull();
    expect(sessionsAtAuthEvents).toEqual([null]);
  });

  describe('a valid link', () => {
    it.each([
      ['a redirect_to in the query', '/login-link?redirect_to=https%3A%2F%2Fevil.example%2F'],
      ['a returnTo in the query', '/login-link?returnTo=%2F%2Fevil.example'],
      ['a next in the query', '/login-link?next=%2Fadmin'],
    ])('lands where the server says, not where the URL says (%s)', async (_label, entry) => {
      seedHandoff(VALID_TOKEN);

      renderPage(entry);

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(screen.queryByText('Admin page')).toBeNull();
    });

    it.each([
      ['an off-site URL', 'https://evil.example/'],
      ['a protocol-relative URL', '//evil.example'],
      ['a backslash path', '/\\evil.example'],
    ])('lands on /account when the server destination is unsafe (%s)', async (_label, redirect) => {
      successRedirect = redirect;
      seedHandoff(VALID_TOKEN);

      renderPage();

      expect(await screen.findByText('Account page')).toBeInTheDocument();
    });

    it('signs in all three roots once the server accepts the token, and announces it only after the session is stored', async () => {
      seedHandoff(VALID_TOKEN);

      renderThreeRoots();

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(await screen.findByText('menu-root: new@example.com')).toBeInTheDocument();
      expect(await screen.findByText('footer-root: new@example.com')).toBeInTheDocument();

      expect(loginLinkRequests()).toEqual([
        {url: expect.stringMatching(/\/mail\/login-link\/$/), authorization: null, body: {token: VALID_TOKEN}},
      ]);
      expect(getStoredSession()).toMatchObject({
        access: NEW_ACCOUNT.access,
        refresh: NEW_ACCOUNT.refresh,
        user: NEW_ACCOUNT.user,
      });
      // One announcement, made with the server-issued session already stored.
      expect(sessionsAtAuthEvents).toEqual([NEW_ACCOUNT.access]);
      expect(handoffToken()).toBeNull();
    });

    it('leaves all three roots signed out when the token was altered', async () => {
      seedHandoff(`${VALID_TOKEN}0`);

      renderThreeRoots();

      await expectUnusableFallback();
      await waitFor(() => expect(loginLinkRequests()).toHaveLength(1));
      expect(screen.getByText('menu-root: signed out')).toBeInTheDocument();
      expect(screen.getByText('footer-root: signed out')).toBeInTheDocument();
      expect(getStoredSession()).toBeNull();
      expect(sessionsAtAuthEvents).toEqual([]);
      expect(linkSpent).toBe(false);
    });
  });
});
