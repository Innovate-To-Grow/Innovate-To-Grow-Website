import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ImpersonateLoginPage} from '@/routes/ImpersonateLoginPage/ImpersonateLoginPage';

const mockImpersonateAutoLogin = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();

vi.mock('@/features/auth/api/session', () => ({
  impersonateAutoLogin: (...args: unknown[]) => mockImpersonateAutoLogin(...args),
}));

vi.mock('@/features/auth/components/context/shared', () => ({
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/impersonate-login" element={<ImpersonateLoginPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('ImpersonateLoginPage', () => {
  beforeEach(() => {
    mockImpersonateAutoLogin.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('navigates to the API-provided redirect when it is safe', async () => {
    mockImpersonateAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: '/schedule',
      next_step: 'account',
      requires_profile_completion: false,
    });

    renderPage('/impersonate-login?token=abc123');

    await waitFor(() => {
      expect(mockImpersonateAutoLogin).toHaveBeenCalledWith('abc123');
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
  });

  it('falls back to /account when the API redirect is unsafe', async () => {
    mockImpersonateAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: 'https://evil.example',
      next_step: 'account',
      requires_profile_completion: false,
    });

    renderPage('/impersonate-login?token=unsafe123');

    await waitFor(() => {
      expect(mockImpersonateAutoLogin).toHaveBeenCalledWith('unsafe123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('shows the error state when the token is rejected', async () => {
    mockImpersonateAutoLogin.mockRejectedValue(new Error('bad token'));

    renderPage('/impersonate-login?token=dead123');

    await waitFor(() => {
      expect(
        screen.getByText('This impersonation link is invalid or has expired.'),
      ).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows the guard message when no token is provided', () => {
    renderPage('/impersonate-login');

    expect(screen.getByText('No impersonation token provided.')).toBeInTheDocument();
    expect(mockImpersonateAutoLogin).not.toHaveBeenCalled();
  });

  it('ignores a successful login that resolves after unmount', async () => {
    let resolveLogin!: (value: unknown) => void;
    mockImpersonateAutoLogin.mockReturnValue(
      new Promise((resolve) => {
        resolveLogin = resolve;
      }),
    );

    const {unmount} = renderPage('/impersonate-login?token=abc123');
    await waitFor(() => expect(mockImpersonateAutoLogin).toHaveBeenCalled());

    unmount();
    await act(async () => {
      resolveLogin({
        message: 'Login successful.',
        access: 'access-token',
        refresh: 'refresh-token',
        user: {member_uuid: '123', email: 'ada@example.com'},
        redirect_to: '/schedule',
        next_step: 'account',
        requires_profile_completion: false,
      });
      await Promise.resolve();
    });

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
  });

  it('ignores a rejected login that settles after unmount', async () => {
    let rejectLogin!: (reason?: unknown) => void;
    mockImpersonateAutoLogin.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectLogin = reject;
      }),
    );

    const {unmount} = renderPage('/impersonate-login?token=dead123');
    await waitFor(() => expect(mockImpersonateAutoLogin).toHaveBeenCalled());

    unmount();
    await act(async () => {
      rejectLogin(new Error('expired'));
      await Promise.resolve();
    });

    expect(
      screen.queryByText('This impersonation link is invalid or has expired.'),
    ).toBeNull();
  });
});
