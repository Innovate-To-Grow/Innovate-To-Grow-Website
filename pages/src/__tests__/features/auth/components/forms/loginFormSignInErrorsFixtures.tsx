import {AxiosError, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';

import {AuthProvider} from '@/features/auth/components/AuthContext';
import {LoginForm} from '@/features/auth/components/forms/LoginForm';

// Exactly what the login view answers once an account's failed attempts are spent.
export const LOCKED_DETAIL =
  'Too many failed sign-in attempts. Please try again later or sign in with an email code.';
export const LOCKED = {status: 429, data: {detail: LOCKED_DETAIL, code: 'login_locked'}};

export interface Reply {
  status: number;
  data: unknown;
}

export const reply = (config: InternalAxiosRequestConfig, {status, data}: Reply) => {
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

export const renderForm = () =>
  render(
    <MemoryRouter>
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    </MemoryRouter>,
  );

export const signInWithPassword = async (identifier = 'ada@example.com', password = 'not-the-password') => {
  fireEvent.click(await screen.findByRole('button', {name: 'Sign in with password instead'}));
  fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: identifier}});
  fireEvent.change(screen.getByLabelText('Password'), {target: {value: password}});
  fireEvent.click(screen.getByRole('button', {name: 'Sign In'}));
};
