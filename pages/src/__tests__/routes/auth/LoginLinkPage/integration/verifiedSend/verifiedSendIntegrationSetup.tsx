import axios, {AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {webcrypto} from 'node:crypto';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, vi} from 'vitest';
import {authApi} from '@/features/auth/api/session/client';
import {captureAuthCallbackParams} from '@/features/auth/api/navigation/callbackParams';
import {persistAuthSession} from '@/features/auth/api/session/storage';
import {AuthProvider} from '@/features/auth/components/AuthContext';
import {solveAltchaChallenge} from '@/features/auth/verification/solve';
import {LoginLinkPage} from '@/routes/auth/LoginLinkPage/LoginLinkPage';
import {STALE_ACCESS, type RecordedRequest, type Reply} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixtures/loginLinkIntegrationFixtures';

export const CODE = '123456';

const OWNER = {
  message: 'Login successful.',
  access: 'owner-access',
  refresh: 'owner-refresh',
  user: {member_uuid: 'member-owner', email: 'owner@example.com'},
  next_step: 'account',
  requires_profile_completion: false,
};

let requests: RecordedRequest[];

export let releaseSessionCheck: () => void;

export let sessionCheckStarted: boolean;

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

export const requestsTo = (suffix: string) => requests.filter((request) => request.url.endsWith(suffix));

// The backend of a browser whose stored session has been revoked: the session
// check is refused, and so is the refresh. The check is held back until the
// test releases it, so the clearing can be timed against the code request.
const backend: AxiosAdapter = async (config) => {
  const url = config.url ?? '';
  const authorization = config.headers.get('Authorization') ?? null;
  const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
  requests.push({url, authorization, body});

  if (url.endsWith('/mail/login-link/')) {
    return reply(config, {
      status: 400,
      data: {detail: 'This login link has expired.', code: 'expired', redirect_to: '/schedule'},
    });
  }
  if (url.endsWith('/authn/session/')) {
    if (authorization === `Bearer ${OWNER.access}`) {
      return reply(config, {status: 200, data: {authenticated: true, user: OWNER.user}});
    }
    sessionCheckStarted = true;
    await new Promise<void>((resolve) => {
      releaseSessionCheck = resolve;
    });
    return reply(config, {status: 401, data: {detail: 'User not found', code: 'user_not_found'}});
  }
  if (url.endsWith('/authn/refresh/')) {
    return reply(config, {status: 401, data: {detail: 'Token is invalid', code: 'token_not_valid'}});
  }
  if (url.endsWith('/authn/send-verification/challenge/')) {
    return reply(config, {
      status: 200,
      data: {
        challenge_id: '11111111-1111-4111-8111-111111111111',
        expires_at: new Date(Date.now() + 300_000).toISOString(),
        algorithm: 'PBKDF2/SHA-256',
        cost: 1,
        challenge: {parameters: {algorithm: 'PBKDF2/SHA-256', cost: 1}},
      },
    });
  }
  if (url.endsWith('/authn/login/request-code/')) {
    return reply(config, {
      status: 200,
      data: {message: 'If an eligible account exists, a verification code has been sent.'},
    });
  }
  if (url.endsWith('/authn/login/verify-code/')) {
    return (body as {code?: string}).code === CODE
      ? reply(config, {status: 200, data: OWNER})
      : reply(config, {status: 400, data: {detail: 'Verification code is invalid or has expired.'}});
  }
  return reply(config, {status: 404, data: {detail: 'Not found.'}});
};

const originalAuthAdapter = authApi.defaults.adapter;

const originalAxiosAdapter = axios.defaults.adapter;

export let proofReached: boolean;

export let finishProof: () => void;

export const renderApp = () =>
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/login-link']}>
        <Routes>
          <Route path="/login-link" element={<LoginLinkPage />} />
          <Route path="/schedule" element={<p>Schedule page</p>} />
          <Route path="/account" element={<p>Account page</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );

export const sendCode = () => {
  fireEvent.change(screen.getByLabelText('Email address'), {target: {value: 'Owner@Example.com'}});
  fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
};

/** The describe's own beforeEach/afterEach: call it first inside the describe. */
export const registerVerifiedSendHooks = () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', webcrypto);
    requests = [];
    sessionCheckStarted = false;
    releaseSessionCheck = () => undefined;
    proofReached = false;
    localStorage.clear();
    sessionStorage.clear();
    authApi.defaults.adapter = backend;
    axios.defaults.adapter = backend;
    // The proof step is held open, so the test decides what happens around it.
    vi.mocked(solveAltchaChallenge)
      .mockReset()
      .mockImplementation(
        () =>
          new Promise<string>((resolve) => {
            proofReached = true;
            finishProof = () => resolve('signed-payload');
          }),
      );
    persistAuthSession({
      access: STALE_ACCESS,
      refresh: 'stale-refresh',
      user: {member_uuid: 'member-old', email: 'old@example.com'},
      requires_profile_completion: false,
    });
    window.history.replaceState(null, '', '/login-link#token=expired-token');
    captureAuthCallbackParams();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    authApi.defaults.adapter = originalAuthAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });
};
