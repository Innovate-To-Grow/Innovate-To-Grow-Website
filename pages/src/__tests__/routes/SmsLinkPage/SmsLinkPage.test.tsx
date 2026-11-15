import {AxiosError, type AxiosResponse} from 'axios';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {captureAuthCallbackParams, readAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {SmsLinkPage} from '@/routes/SmsLinkPage/SmsLinkPage';

const mockOpenSmsLink = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();

vi.mock('@/features/auth/api/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/session')>()),
  openSmsLink: (...args: unknown[]) => mockOpenSmsLink(...args),
}));

vi.mock('@/features/auth/components/context/shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/components/context/shared')>()),
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {...actual, useNavigate: () => mockNavigate};
});

const TOKEN = 'AbCdEfGhIjKlMnOpQrStUv';

const rejection = (status: number, data: unknown = {}) =>
  new AxiosError('failed', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    data,
    statusText: '',
    headers: {},
    config: {headers: {}},
  } as unknown as AxiosResponse);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/l" element={<SmsLinkPage />} />
        <Route path="/l/:token" element={<SmsLinkPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** The token as the app finds it after start-up moved it out of the address. */
function captureToken(token = TOKEN) {
  window.history.replaceState({}, '', `/l/${token}`);
  captureAuthCallbackParams();
}

describe('SmsLinkPage', () => {
  beforeEach(() => {
    mockOpenSmsLink.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
  });

  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('sends the visitor on for a shared link, without signing anyone in', async () => {
    captureToken();
    mockOpenSmsLink.mockResolvedValue({kind: 'redirect', redirectTo: '/event-registration?event=fall'});

    renderAt('/l');

    expect(screen.getByRole('status')).toHaveTextContent('Opening your link...');
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/event-registration?event=fall', {replace: true}));
    expect(mockOpenSmsLink).toHaveBeenCalledWith(TOKEN);
    expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
    expect(readAuthCallbackParams('sms-link', new URLSearchParams()).get('token')).toBeNull();
  });

  it('signs in with a personal link and lands where it says', async () => {
    mockOpenSmsLink.mockResolvedValue({
      kind: 'sign_in',
      login: {next_step: 'account', redirect_to: '/subscribe', requires_profile_completion: false},
    });

    renderAt(`/l/${TOKEN}`);

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/subscribe', {replace: true}));
    expect(mockDispatchAuthStateChange).toHaveBeenCalledTimes(1);
  });

  it('never follows an off-site destination', async () => {
    mockOpenSmsLink.mockResolvedValue({kind: 'redirect', redirectTo: '//evil.example'});
    renderAt(`/l/${TOKEN}`);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', {replace: true}));
  });

  it('offers the sign-in page, back to the link’s page, when the link has expired', async () => {
    captureToken();
    mockOpenSmsLink.mockRejectedValue(rejection(400, {code: 'expired', redirect_to: '/account'}));

    renderAt('/l');

    expect(await screen.findByText(/This link has expired\./)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Sign in'})).toHaveAttribute('href', '/login?returnTo=%2Faccount');
    expect(screen.queryByRole('button', {name: 'Try the link again'})).not.toBeInTheDocument();
    expect(readAuthCallbackParams('sms-link', new URLSearchParams()).get('token')).toBeNull();
  });

  it('can try again when the server could not be reached', async () => {
    mockOpenSmsLink
      .mockRejectedValueOnce(rejection(503))
      .mockResolvedValueOnce({kind: 'redirect', redirectTo: '/schedule'});

    renderAt(`/l/${TOKEN}`);

    fireEvent.click(await screen.findByRole('button', {name: 'Try the link again'}));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true}));
    expect(mockOpenSmsLink).toHaveBeenCalledTimes(2);
  });

  it('says a link without a token cannot be used', () => {
    renderAt('/l');
    expect(screen.getByText(/This link can't be used\./)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Sign in'})).toHaveAttribute('href', '/login');
    expect(mockOpenSmsLink).not.toHaveBeenCalled();
  });

  it('falls back when leaving the page fails after the exchange', async () => {
    mockOpenSmsLink.mockResolvedValue({kind: 'redirect', redirectTo: '/schedule'});
    mockNavigate.mockImplementation(() => {
      throw new Error('navigation failed');
    });

    renderAt(`/l/${TOKEN}`);

    expect(await screen.findByText(/We couldn't open your link right now\./)).toBeInTheDocument();
    await act(async () => {});
  });
});
