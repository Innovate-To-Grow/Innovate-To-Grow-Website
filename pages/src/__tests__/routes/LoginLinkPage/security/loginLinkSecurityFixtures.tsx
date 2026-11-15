import {AxiosError, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {expect} from 'vitest';

import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/navigation/callbackParams';
import {persistAuthSession} from '@/features/auth/api/session/storage';
import {LoginLinkPage} from '@/routes/LoginLinkPage/LoginLinkPage';

export const VALID_TOKEN = 'valid-emailed-token';
export const HANDOFF_KEY = 'i2g_callback_params:login-link';
const UNUSABLE = "This sign-in link can't be used.";

export const NEW_ACCOUNT = {
  message: 'Login successful.',
  access: 'new-access',
  refresh: 'new-refresh',
  user: {member_uuid: 'member-new', email: 'new@example.com'},
  requires_profile_completion: false,
};

export interface RecordedRequest {
  url: string;
  authorization: unknown;
  body: unknown;
}

type Reply = {status: number; data: unknown};

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

// What main.tsx does before React mounts: the token moves into the
// sessionStorage handoff and the URL is scrubbed.
export const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  captureAuthCallbackParams();
};

export const handoffToken = () => readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

// A session a visitor wrote into localStorage by hand: well-formed, never issued.
export const seedForgedSession = () =>
  persistAuthSession({
    access: 'forged-access',
    refresh: 'forged-refresh',
    user: {member_uuid: 'member-forged', email: 'forged@example.com', is_staff: true},
    requires_profile_completion: false,
  });

export const appRoutes = (entry: string) => (
  <MemoryRouter initialEntries={[entry]}>
    <Routes>
      <Route path="/login-link" element={<LoginLinkPage />} />
      <Route path="/schedule" element={<p>Schedule page</p>} />
      <Route path="/account" element={<p>Account page</p>} />
      <Route path="/admin" element={<p>Admin page</p>} />
    </Routes>
  </MemoryRouter>
);

// The page alone: no provider runs its own session check, so every request and
// every auth event below comes from the page.
export const renderPage = (entry = '/login-link') => render(appRoutes(entry));

export const expectUnusableFallback = async () => {
  expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent(UNUSABLE);
  expect(screen.queryByText('Schedule page')).toBeNull();
  expect(screen.queryByText('Account page')).toBeNull();
  expect(screen.queryByText('Admin page')).toBeNull();
};
