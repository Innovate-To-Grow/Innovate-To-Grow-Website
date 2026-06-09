import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {LoginLinkPage} from '../LoginLinkPage';

const mockLoginLinkAutoLogin = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();
const mockGetAccessToken = vi.fn();

vi.mock('@/features/auth', () => ({
  loginLinkAutoLogin: (...args: unknown[]) => mockLoginLinkAutoLogin(...args),
}));

vi.mock('@/features/auth/api/storage', () => ({
  getAccessToken: () => mockGetAccessToken(),
}));

vi.mock('@/features/auth/components/context/shared', () => ({
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/login-link" element={<LoginLinkPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('LoginLinkPage', () => {
  beforeEach(() => {
    mockLoginLinkAutoLogin.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
    mockGetAccessToken.mockReset();
    mockGetAccessToken.mockReturnValue(null);
  });

  it('navigates to the API-provided redirect when it is safe', async () => {
    mockLoginLinkAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: '/schedule',
    });

    renderPage('/login-link?token=abc123');

    await waitFor(() => {
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('abc123');
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
  });

  it('falls back to /account when the API redirect is unsafe', async () => {
    mockLoginLinkAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: 'https://evil.example',
    });

    renderPage('/login-link?token=unsafe123');

    await waitFor(() => {
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('unsafe123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('prefers complete-profile when the API says the account is incomplete', async () => {
    mockLoginLinkAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    });

    renderPage('/login-link?token=incomplete123');

    await waitFor(() => {
      expect(mockLoginLinkAutoLogin).toHaveBeenCalledWith('incomplete123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fschedule', {replace: true});
  });

  it('shows the error state when the token is rejected and no session exists', async () => {
    mockLoginLinkAutoLogin.mockRejectedValue(new Error('bad token'));

    renderPage('/login-link?token=dead123');

    await waitFor(() => {
      expect(
        screen.getByText('This login link is invalid or has expired. Please log in manually.'),
      ).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('continues to /account when the token is rejected but a session is stored', async () => {
    mockLoginLinkAutoLogin.mockRejectedValue(new Error('already used'));
    mockGetAccessToken.mockReturnValue('stored-access-token');

    const {container} = renderPage('/login-link?token=used123');

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
    });
    // Scoped to this render: RTL auto-cleanup is off in this suite, so a
    // global screen query would see earlier tests' DOM.
    expect(container.querySelector('.magic-login-error')).toBeNull();
  });

  it('shows the guard message when no token is provided', () => {
    renderPage('/login-link');

    expect(screen.getByText('No login token provided.')).toBeInTheDocument();
    expect(mockLoginLinkAutoLogin).not.toHaveBeenCalled();
  });
});
