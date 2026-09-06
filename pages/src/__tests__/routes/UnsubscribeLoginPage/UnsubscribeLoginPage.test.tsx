import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {UnsubscribeLoginPage} from '@/routes/UnsubscribeLoginPage/UnsubscribeLoginPage';

const mockUnsubscribeAutoLogin = vi.fn();

vi.mock('@/features/auth', () => ({
  unsubscribeAutoLogin: (...args: unknown[]) => mockUnsubscribeAutoLogin(...args),
}));

const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/unsubscribe-login" element={<UnsubscribeLoginPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('UnsubscribeLoginPage', () => {
  beforeEach(() => {
    mockUnsubscribeAutoLogin.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the unsubscribed confirmation after a successful auto-login', async () => {
    mockUnsubscribeAutoLogin.mockResolvedValue({message: 'Unsubscribed.'});

    renderPage('/unsubscribe-login?token=abc123');

    expect(screen.getByText('Unsubscribing you...')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockUnsubscribeAutoLogin).toHaveBeenCalledWith('abc123');
    });

    await waitFor(() => {
      expect(
        screen.getByText('You have been unsubscribed from updates and announcements.'),
      ).toBeInTheDocument();
    });
  });

  it('shows the error state when the token is rejected', async () => {
    mockUnsubscribeAutoLogin.mockRejectedValue(new Error('bad token'));

    renderPage('/unsubscribe-login?token=dead123');

    await waitFor(() => {
      expect(
        screen.getByText(
          'This unsubscribe link is invalid or has expired. Please update your email preferences manually.',
        ),
      ).toBeInTheDocument();
    });
  });

  it('shows the guard message when no token is provided', () => {
    renderPage('/unsubscribe-login');

    expect(screen.getByText('No unsubscribe token provided.')).toBeInTheDocument();
    expect(mockUnsubscribeAutoLogin).not.toHaveBeenCalled();
  });

  it('ignores a successful unsubscribe that resolves after unmount', async () => {
    let resolveLogin!: (value: unknown) => void;
    mockUnsubscribeAutoLogin.mockReturnValue(
      new Promise((resolve) => {
        resolveLogin = resolve;
      }),
    );

    const {unmount} = renderPage('/unsubscribe-login?token=abc123');
    await waitFor(() => expect(mockUnsubscribeAutoLogin).toHaveBeenCalled());

    unmount();
    await act(async () => {
      resolveLogin({message: 'Unsubscribed.'});
      await Promise.resolve();
    });

    expect(
      screen.queryByText('You have been unsubscribed from updates and announcements.'),
    ).toBeNull();
  });

  it('ignores a rejected unsubscribe that settles after unmount', async () => {
    let rejectLogin!: (reason?: unknown) => void;
    mockUnsubscribeAutoLogin.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectLogin = reject;
      }),
    );

    const {unmount} = renderPage('/unsubscribe-login?token=dead123');
    await waitFor(() => expect(mockUnsubscribeAutoLogin).toHaveBeenCalled());

    unmount();
    await act(async () => {
      rejectLogin(new Error('expired'));
      await Promise.resolve();
    });

    expect(
      screen.queryByText(
        'This unsubscribe link is invalid or has expired. Please update your email preferences manually.',
      ),
    ).toBeNull();
  });
});
