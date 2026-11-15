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
import axios, {type AxiosAdapter, type InternalAxiosRequestConfig} from 'axios';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {authApi} from '@/features/auth/api/session/client';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {LoginLinkPage} from '@/routes/auth/LoginLinkPage/LoginLinkPage';
import {
  EMAILED_TOKEN,
  NEW_ACCOUNT,
  type RecordedRequest,
  type Reply,
  reply,
  seedHandoff,
  seedStaleSession,
  STALE_ACCESS,
  useAdapter,
} from '@/__tests__/routes/auth/LoginLinkPage/integration/loginLinkIntegrationFixtures';

const mockRequestLoginCode = vi.fn();

// The code request runs a proof-of-work challenge against three extra endpoints;
// that machinery has its own tests. Everything after it (verify, storage, the
// provider, the event) is real.
vi.mock('@/features/auth/api/signin/flows', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/signin/flows')>()),
  requestLoginCode: (...args: unknown[]) => mockRequestLoginCode(...args),
}));

let requests: RecordedRequest[];

const record = (config: InternalAxiosRequestConfig): RecordedRequest => {
  const request = {
    url: config.url ?? '',
    authorization: config.headers.get('Authorization') ?? null,
    body: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
  };
  requests.push(request);
  return request;
};

const requestsTo = (suffix: string) => requests.filter((request) => request.url.endsWith(suffix));
const refreshRequests = () => requestsTo('/authn/refresh/');
const loginLinkRequests = () => requestsTo('/mail/login-link/');

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
