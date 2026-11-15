// Only the server's verdict on an emailed token may sign anyone in. Nothing the
// visitor controls (the URL, the sessionStorage handoff, a session stored in
// localStorage) authorizes a sign-in, a session, or a protected destination on
// its own. Driven through the REAL auth client, storage, callback handoff, page
// and providers against a fake axios adapter that answers like LoginLinkView.
import axios, {type AxiosAdapter, type InternalAxiosRequestConfig} from 'axios';
import {cleanup, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {authApi} from '@/features/auth/api/session/client';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {
  NEW_ACCOUNT,
  type RecordedRequest,
  renderPage,
  reply,
  seedForgedSession,
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
});
