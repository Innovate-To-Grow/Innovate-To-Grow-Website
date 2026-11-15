import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';

import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/navigation/callbackParams';
import {
  LoginLinkFallback,
  type LoginLinkFallbackKind,
} from '@/routes/LoginLinkPage/LoginLinkFallback';

export const INSTEAD = "Enter your email and we'll send you a 6-digit code to sign in instead.";
export const GENERIC_ACK = 'If an eligible account exists, a verification code has been sent.';

export const renderFallback = (
  props: {kind?: LoginLinkFallbackKind; returnTo?: string | null; onRetry?: () => void} = {},
) =>
  render(
    <MemoryRouter>
      <LoginLinkFallback kind={props.kind ?? 'invalid'} returnTo={props.returnTo ?? null} onRetry={props.onRetry} />
    </MemoryRouter>,
  );

// What main.tsx does before React mounts: the token moves into the
// sessionStorage handoff and the URL is scrubbed.
export const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  captureAuthCallbackParams();
};
export const handoffToken = () => readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

export const emailField = () => screen.getByLabelText('Email address');
export const submit = () => fireEvent.click(screen.getByRole('button', {name: /Send sign-in code|Sending code/}));
export const typeEmail = (value: string) => fireEvent.change(emailField(), {target: {value}});
export const codeField = () => screen.getByRole('textbox', {name: '6-digit verification code'});
export const codeHeading = () => screen.findByRole('heading', {name: 'Verify Login', level: 1});
