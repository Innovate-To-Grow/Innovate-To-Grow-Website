// What the password form shows when the server refuses a sign-in, with the real
// stack from the form down to the wire: AuthProvider, the auth actions, the
// login flow, and the shared client run against a fake axios adapter that
// answers with the backend's own bodies. Only the RSA step, which needs a key
// from the server, is replaced.
import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

vi.mock('@/lib/security', () => ({
  clearKeyCache: vi.fn(),
  encryptPasswordWithCurrentKey: async (password: string) => ({
    encryptedPassword: `encrypted:${password}`,
    keyId: 'key-1',
  }),
}));

import {authApi} from '@/features/auth/api/client';
import {AuthProvider} from '@/features/auth/components/AuthContext';
import {LoginForm} from '@/features/auth/components/forms/LoginForm';

// Exactly what the login view answers once an account's failed attempts are spent.
const LOCKED_DETAIL =
  'Too many failed sign-in attempts. Please try again later or sign in with an email code.';
const LOCKED = {status: 429, data: {detail: LOCKED_DETAIL, code: 'login_locked'}};

interface Reply {
  status: number;
  data: unknown;
}

let loginReply: Reply;
let loginBodies: unknown[];

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

const backend: AxiosAdapter = async (config) => {
  if ((config.url ?? '').endsWith('/authn/login/')) {
    loginBodies.push(typeof config.data === 'string' ? JSON.parse(config.data) : config.data);
    return reply(config, loginReply);
  }
  return reply(config, {status: 404, data: {detail: 'Not found.'}});
};

const renderForm = () =>
  render(
    <MemoryRouter>
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    </MemoryRouter>,
  );

const signInWithPassword = async (identifier = 'ada@example.com', password = 'not-the-password') => {
  fireEvent.click(await screen.findByRole('button', {name: 'Sign in with password instead'}));
  fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: identifier}});
  fireEvent.change(screen.getByLabelText('Password'), {target: {value: password}});
  fireEvent.click(screen.getByRole('button', {name: 'Sign In'}));
};

describe('LoginForm password sign-in refusals', () => {
  const originalAdapter = authApi.defaults.adapter;
  const originalAxiosAdapter = axios.defaults.adapter;

  beforeEach(() => {
    loginBodies = [];
    loginReply = LOCKED;
    localStorage.clear();
    sessionStorage.clear();
    authApi.defaults.adapter = backend;
    axios.defaults.adapter = backend;
  });

  afterEach(() => {
    cleanup();
    authApi.defaults.adapter = originalAdapter;
    axios.defaults.adapter = originalAxiosAdapter;
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('a locked-out account (429, login_locked)', () => {
    it("shows the server's message, which points to the email code", async () => {
      renderForm();

      await signInWithPassword();

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent(LOCKED_DETAIL);
      expect(alert.textContent).toMatch(/email code/);
      expect(alert).toHaveClass('auth-alert', 'error');
      expect(loginBodies).toEqual([{email: 'ada@example.com', password: 'encrypted:not-the-password', key_id: 'key-1'}]);
    });

    it('keeps the visitor on the password form, with the email-code switch right there', async () => {
      renderForm();

      await signInWithPassword();
      await screen.findByRole('alert');

      expect(screen.getByLabelText('Email or Phone')).toHaveValue('ada@example.com');
      expect(screen.getByRole('button', {name: 'Sign In'})).toBeInTheDocument();
      expect(screen.getByRole('button', {name: 'Sign in with a verification code'})).toBeEnabled();
    });

    it('shows the same message for a phone number', async () => {
      renderForm();

      await signInWithPassword('(202) 555-0123');

      expect(await screen.findByRole('alert')).toHaveTextContent(LOCKED_DETAIL);
      expect(loginBodies).toMatchObject([{email: '2025550123'}]);
    });

    it('moves on to the code sign-in through the switch, with the message gone', async () => {
      renderForm();
      await signInWithPassword();
      await screen.findByRole('alert');

      fireEvent.click(screen.getByRole('button', {name: 'Sign in with a verification code'}));

      expect(screen.getByLabelText('Email or phone number')).toBeInTheDocument();
      expect(screen.queryByRole('alert')).toBeNull();
      expect(screen.queryByText(LOCKED_DETAIL)).toBeNull();
    });

    it('carries the address typed in the password form over to the code form', async () => {
      renderForm();
      await signInWithPassword('ada@example.com');
      await screen.findByRole('alert');

      fireEvent.click(screen.getByRole('button', {name: 'Sign in with a verification code'}));

      expect(screen.getByLabelText('Email or phone number')).toHaveValue('ada@example.com');
    });

    it('does not overwrite something already typed in the code form', async () => {
      renderForm();
      fireEvent.change(await screen.findByLabelText('Email or phone number'), {
        target: {value: 'first@example.com'},
      });
      fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
      fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'second@example.com'}});

      fireEvent.click(screen.getByRole('button', {name: 'Sign in with a verification code'}));

      expect(screen.getByLabelText('Email or phone number')).toHaveValue('first@example.com');
    });

    it('goes away when the visitor edits the password', async () => {
      renderForm();
      await signInWithPassword();
      await screen.findByRole('alert');

      fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'another-try'}});

      expect(screen.queryByRole('alert')).toBeNull();
    });

    it("shows a different server message as it came, and the fallback when there is none", async () => {
      loginReply = {status: 429, data: {detail: 'Locked for now.', code: 'login_locked'}};
      renderForm();
      await signInWithPassword();
      expect(await screen.findByRole('alert')).toHaveTextContent('Locked for now.');
      cleanup();

      loginReply = {status: 429, data: {code: 'login_locked'}};
      renderForm();
      await signInWithPassword();
      expect(await screen.findByRole('alert')).toHaveTextContent(LOCKED_DETAIL);
    });
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
});
