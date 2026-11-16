// Only the server's verdict on an emailed token may sign anyone in. Nothing the
// visitor controls (the URL, the sessionStorage handoff, a session stored in
// localStorage) authorizes a sign-in, a session, or a protected destination on
// its own. Driven through the REAL auth client, storage, callback handoff, page
// and providers against a fake axios adapter that answers like LoginLinkView.
import axios, {type AxiosAdapter, type InternalAxiosRequestConfig} from 'axios';
import {cleanup} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {authApi} from '@/features/auth/api/session/client';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {
  expectUnusableFallback,
  HANDOFF_KEY,
  handoffToken,
  NEW_ACCOUNT,
  type RecordedRequest,
  renderPage,
  reply,
  seedForgedSession,
  seedHandoff,
  VALID_TOKEN,
} from '@/__tests__/routes/auth/LoginLinkPage/security/loginLinkSecurityFixtures';

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
});
