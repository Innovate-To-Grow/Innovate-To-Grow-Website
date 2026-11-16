import {AxiosError, type AxiosResponse} from 'axios';
import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {expect} from 'vitest';

import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/navigation/callbackParams';

import {LoginLinkPage} from '@/routes/LoginLinkPage/LoginLinkPage';

export const INSTEAD = "Enter your email and we'll send you a 6-digit code to sign in instead.";
export const NOTICE = {
  expired: 'This sign-in link has expired.',
  used: 'This sign-in link has already been used.',
  retryable: "We couldn't verify your sign-in link right now.",
  unusable: "This sign-in link can't be used.",
};

export const RETRY = 'Try the link again';

export const STORED_SESSION = {
  version: 1,
  generation: 'stored-generation',
  access: 'stored-access-token',
  refresh: 'stored-refresh-token',
  user: {member_uuid: 'stored-member', email: 'stored@example.com'},
  requires_profile_completion: false,
};

export const httpError = (status: number, data?: unknown) =>
  new AxiosError(
    `Request failed with status code ${status}`,
    status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
    undefined,
    undefined,
    {status, statusText: '', headers: {}, config: {}, data} as AxiosResponse,
  );

// Stores the token the way main.tsx does before React mounts: captured into the
// sessionStorage handoff, with the URL scrubbed.
export const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  captureAuthCallbackParams();
};

export const handoffToken = () =>
  readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

export const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/login-link" element={<LoginLinkPage />} />
      </Routes>
    </MemoryRouter>,
  );

/**
 * A link that cannot be used is not an error: no alert, no error text, just an
 * informational notice and the inline email-code sign-in.
 */
export const expectFallback = (container: HTMLElement, firstSentence: string) => {
  const notice = screen.getByRole('status');
  expect(notice).toHaveClass('auth-alert', 'info');
  expect(notice.textContent).toBe(`${firstSentence} ${INSTEAD}`);
  expect(screen.getByRole('heading', {name: 'Sign in to I2G', level: 1})).toBeInTheDocument();
  expect(screen.getByLabelText('Email address')).toHaveAttribute('type', 'email');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(container.querySelector('.magic-login-error')).toBeNull();
  expect(container.querySelector('.auth-alert.error')).toBeNull();
};
