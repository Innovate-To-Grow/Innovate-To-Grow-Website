import axios, {type AxiosAdapter, type InternalAxiosRequestConfig} from 'axios';
import {cleanup} from '@testing-library/react';

import {afterEach, beforeEach, vi, type Mock} from 'vitest';
import {authApi} from '@/features/auth/api/session/client';

import {STALE_ACCESS, MEMBER_B, NEW_ACCOUNT, type RecordedRequest, type Reply, reply, useAdapter} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixtures/loginLinkIntegrationFixtures';

export let requests: RecordedRequest[];

const record = (config: InternalAxiosRequestConfig): RecordedRequest => {
  const request = {
    url: config.url ?? '',
    authorization: config.headers.get('Authorization') ?? null,
    body: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
  };
  requests.push(request);
  return request;
};

export const requestsTo = (suffix: string) => requests.filter((request) => request.url.endsWith(suffix));

export const refreshRequests = () => requestsTo('/authn/refresh/');

export const loginLinkRequests = () => requestsTo('/mail/login-link/');

const originalAuthAdapter = authApi.defaults.adapter;

const originalAxiosAdapter = axios.defaults.adapter;

export const TOKENS = {
  expired: 'expired-token',
  used: 'used-token',
  unknown: 'unknown-token',
  flaky: 'flaky-token',
  html: 'html-token',
  ok: 'ok-token',
};

export const GOOD_CODE = '123456';

// What the backend puts in the 400 bodies of an expired or used link: the
// link's own post-login destination (undefined = an older backend).
let linkRedirect: unknown;

// ...and what a buggy backend might add to an invalid link (it must be ignored).
let invalidLinkRedirect: unknown;

export let flakyCalls: number;

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

export const verifyResponse = {
  ...sessionFields,
  next_step: 'account',
  requires_profile_completion: false,
};

const MEMBER_B_ACCESS = 'b-access';

export const memberBResponse = {
  ...verifyResponse,
  access: MEMBER_B_ACCESS,
  refresh: 'b-refresh',
  user: MEMBER_B,
};

// The fixed backend: the exchange endpoints run no authentication at all, so
// the stored bearer is irrelevant to them.
export const fixedBackend: AxiosAdapter = (config) => {
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

export const setLinkRedirect = (value: typeof linkRedirect) => {
  linkRedirect = value;
};
export const setInvalidLinkRedirect = (value: typeof invalidLinkRedirect) => {
  invalidLinkRedirect = value;
};
export const setCodeReply = (value: typeof codeReply) => {
  codeReply = value;
};
export const setCodeAccount = (value: typeof codeAccount) => {
  codeAccount = value;
};

/** The describe's own beforeEach/afterEach: call it first inside the describe. */
export const registerFallbackHooks = (mockRequestLoginCode: Mock) => {
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
};
