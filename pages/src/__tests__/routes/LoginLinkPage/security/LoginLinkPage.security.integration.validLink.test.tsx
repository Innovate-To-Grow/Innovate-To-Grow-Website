// Only the server's verdict on an emailed token may sign anyone in. Nothing the
// visitor controls (the URL, the sessionStorage handoff, a session stored in
// localStorage) authorizes a sign-in, a session, or a protected destination on
// its own. Driven through the REAL auth client, storage, callback handoff, page
// and providers against a fake axios adapter that answers like LoginLinkView.
import axios, {type AxiosAdapter, type InternalAxiosRequestConfig} from 'axios';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {authApi} from '@/features/auth/api/session/client';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {AuthProvider, useAuth} from '@/features/auth/components/AuthContext';
import {
  appRoutes,
  expectUnusableFallback,
  handoffToken,
  NEW_ACCOUNT,
  type RecordedRequest,
  renderPage,
  reply,
  seedHandoff,
  VALID_TOKEN,
} from '@/__tests__/routes/LoginLinkPage/security/loginLinkSecurityFixtures';

let requests: RecordedRequest[];
let linkSpent: boolean;
let successRedirect: unknown;

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
