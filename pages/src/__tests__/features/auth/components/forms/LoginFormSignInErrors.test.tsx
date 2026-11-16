// What the password form shows when the server refuses a sign-in, with the real
// stack from the form down to the wire: AuthProvider, the auth actions, the
// login flow, and the shared client run against a fake axios adapter that
// answers with the backend's own bodies. Only the RSA step, which needs a key
// from the server, is replaced.
import axios, {type AxiosAdapter} from 'axios';
import {cleanup, fireEvent, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

vi.mock('@/lib/security', () => ({
  clearKeyCache: vi.fn(),
  encryptPasswordWithCurrentKey: async (password: string) => ({
    encryptedPassword: `encrypted:${password}`,
    keyId: 'key-1',
  }),
}));

import {authApi} from '@/features/auth/api/session/client';
import {setVerifiedSendStatus} from '@/features/auth/verification/status';
import {LOCKED, LOCKED_DETAIL, renderForm, type Reply, reply, signInWithPassword} from '@/__tests__/features/auth/components/forms/loginFormSignInErrorsFixtures';

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
});
