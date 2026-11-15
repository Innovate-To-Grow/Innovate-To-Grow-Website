// What the password form shows when the server refuses a sign-in, with the real
// stack from the form down to the wire: AuthProvider, the auth actions, the
// login flow, and the shared client run against a fake axios adapter that
// answers with the backend's own bodies. Only the RSA step, which needs a key
// from the server, is replaced.
import axios, {type AxiosAdapter} from 'axios';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

vi.mock('@/lib/security', () => ({
  clearKeyCache: vi.fn(),
  encryptPasswordWithCurrentKey: async (password: string) => ({
    encryptedPassword: `encrypted:${password}`,
    keyId: 'key-1',
  }),
}));

import {authApi} from '@/features/auth/api/session/client';
import {AuthProvider} from '@/features/auth/components/AuthContext';
import {VerifiedSendStatus} from '@/features/auth/verification/VerifiedSendStatus';
import {setVerifiedSendStatus} from '@/features/auth/verification/status';
import {LOCKED, renderForm, type Reply, reply, signInWithPassword} from '@/__tests__/features/auth/components/forms/loginFormSignInErrorsFixtures';

let loginReply: Reply;
let codeReply: Reply | null;
let loginBodies: unknown[];

const backend: AxiosAdapter = async (config) => {
  if ((config.url ?? '').endsWith('/authn/login/')) {
    loginBodies.push(typeof config.data === 'string' ? JSON.parse(config.data) : config.data);
    return reply(config, loginReply);
  }
  if ((config.url ?? '').endsWith('/authn/email-auth/request-code/') && codeReply) {
    return reply(config, codeReply);
  }
  return reply(config, {status: 404, data: {detail: 'Not found.'}});
};

describe('LoginForm password sign-in refusals', () => {
  const originalAdapter = authApi.defaults.adapter;
  const originalAxiosAdapter = axios.defaults.adapter;

  beforeEach(() => {
    loginBodies = [];
    loginReply = LOCKED;
    codeReply = null;
    localStorage.clear();
    sessionStorage.clear();
    authApi.defaults.adapter = backend;
    axios.defaults.adapter = backend;
  });

  afterEach(() => {
    cleanup();
    setVerifiedSendStatus({phase: 'idle', message: ''});
    authApi.defaults.adapter = originalAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('every other refusal is shown as before', () => {
    it('wrong credentials', async () => {
      loginReply = {status: 400, data: {non_field_errors: ['Invalid credentials.']}};
      renderForm();

      await signInWithPassword();

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent('Invalid credentials.');
      expect(alert.textContent).not.toMatch(/email code|failed sign-in/i);
    });

    it('a throttle that is not the lock-out', async () => {
      loginReply = {status: 429, data: {detail: 'Request was throttled. Expected available in 30 seconds.'}};
      renderForm();

      await signInWithPassword();

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent('Request was throttled. Expected available in 30 seconds.');
      expect(alert.textContent).not.toMatch(/failed sign-in/i);
    });

    it('a 429 with nothing to show', async () => {
      loginReply = {status: 429, data: {code: 'something_else'}};
      renderForm();

      await signInWithPassword();

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Request failed. Please check your input and try again.',
      );
    });

    it('a server error', async () => {
      loginReply = {status: 500, data: {}};
      renderForm();

      await signInWithPassword();

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('A server error occurred. Please try again later.');
      });
    });
  });

  it('shows a throttled email-code request once inside the login form, without the raw Axios error in either React root', async () => {
    codeReply = {
      status: 429,
      data: {detail: 'Please wait before requesting another code.', code: 'send_throttled'},
    };
    // Production mounts a separate AuthProvider for the menu and the main app.
    render(<AuthProvider><div data-testid="menu-root" /></AuthProvider>);
    renderForm();
    render(<VerifiedSendStatus />);

    fireEvent.change(await screen.findByLabelText('Email or phone number'), {
      target: {value: 'ada@example.com'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Please wait before requesting another code.');
    expect(screen.getAllByRole('alert')).toHaveLength(1);

    // The app's one progress indicator must not display a raw transport error,
    // even if another caller publishes an error state.
    act(() => setVerifiedSendStatus({phase: 'error', message: 'Request failed with status code 429'}));
    expect(screen.queryAllByText('Request failed with status code 429')).toHaveLength(0);
    expect(document.querySelectorAll('.verified-send-status')).toHaveLength(0);
  });
});
