// The fallback's code request goes through the REAL verified-send machinery
// (challenge, proof of work, send) against a fake axios adapter; only the proof
// solver, which needs a browser worker, is replaced. Everything else on the way
// (flows, client, storage, AuthProvider, page) is real.
//
// It reproduces a race that no other test can reach because the shared test
// setup stubs the machinery out: a browser holding a DEAD stored session has it
// cleared by the provider's own check (session 401, then refresh 401) while the
// visitor's code request is still on its way. The stored session's generation
// changes mid-flight; a code request does not depend on it, so the request must
// not be cancelled and the visitor must not see an error.
import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import {webcrypto} from 'node:crypto';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

vi.unmock('@/features/auth/verification');
vi.mock('@/features/auth/verification/solve', () => ({
  newRequestId: () => '22222222-2222-4222-8222-222222222222',
  solveAltchaChallenge: vi.fn(),
}));

import {authApi} from '@/features/auth/api/client';
import {captureAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {getStoredSession, persistAuthSession} from '@/features/auth/api/storage';
import {AuthProvider} from '@/features/auth/components/AuthContext';
import {solveAltchaChallenge} from '@/features/auth/verification/solve';
import {LoginLinkPage} from '@/routes/LoginLinkPage/LoginLinkPage';

const STALE_ACCESS = 'stale-access';
const CODE = '123456';

const OWNER = {
  message: 'Login successful.',
  access: 'owner-access',
  refresh: 'owner-refresh',
  user: {member_uuid: 'member-owner', email: 'owner@example.com'},
  next_step: 'account',
  requires_profile_completion: false,
};

interface RecordedRequest {
  url: string;
  authorization: unknown;
  body: unknown;
}

type Reply = {status: number; data: unknown};

let requests: RecordedRequest[];
let releaseSessionCheck: () => void;
let sessionCheckStarted: boolean;

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

const requestsTo = (suffix: string) => requests.filter((request) => request.url.endsWith(suffix));

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

describe('LoginLinkPage code fallback with the real verified send', () => {
  const originalAuthAdapter = authApi.defaults.adapter;
  const originalAxiosAdapter = axios.defaults.adapter;

  let proofReached: boolean;
  let finishProof: () => void;

  const renderApp = () =>
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

  const sendCode = () => {
    fireEvent.change(screen.getByLabelText('Email address'), {target: {value: 'Owner@Example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
  };

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

  it('is not cancelled when the dead stored session is cleared while the request is in flight', async () => {
    const generationBefore = getStoredSession()?.generation;
    expect(generationBefore).toBeTruthy();
    renderApp();
    await screen.findByLabelText('Email address');
    // The provider's check of the stale session is under way but unanswered.
    await waitFor(() => expect(sessionCheckStarted).toBe(true));

    sendCode();
    await waitFor(() => expect(proofReached).toBe(true));
    expect(requestsTo('/authn/login/request-code/')).toHaveLength(0);

    // The check now learns the session is dead and clears it: the stored
    // generation the send started under is gone before the proof is finished.
    releaseSessionCheck();
    await waitFor(() => expect(getStoredSession()).toBeNull());
    finishProof();

    // The visitor moves on to the code step: no error, nothing to redo.
    expect(await screen.findByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(/unexpected error/i)).toBeNull();
    expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toHaveFocus();

    // Exactly one code was requested, for the lowercased address, and the
    // request carried the solved proof.
    const sent = requestsTo('/authn/login/request-code/');
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toMatchObject({
      email: 'owner@example.com',
      verification_challenge_id: '11111111-1111-4111-8111-111111111111',
      verification_payload: 'signed-payload',
      send_request_id: '22222222-2222-4222-8222-222222222222',
    });
    expect(requestsTo('/authn/email-auth/request-code/')).toHaveLength(0);

    // ...and the code then signs the visitor in as the link's owner.
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: CODE}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-owner'}});
    expect(requestsTo('/authn/login/verify-code/')[0]).toMatchObject({authorization: null});
  });

  it('is not cancelled when the session was already cleared before the request started', async () => {
    renderApp();
    await screen.findByLabelText('Email address');
    await waitFor(() => expect(sessionCheckStarted).toBe(true));
    releaseSessionCheck();
    await waitFor(() => expect(getStoredSession()).toBeNull());

    sendCode();
    await waitFor(() => expect(proofReached).toBe(true));
    finishProof();

    expect(await screen.findByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(requestsTo('/authn/login/request-code/')).toHaveLength(1);
  });
});
