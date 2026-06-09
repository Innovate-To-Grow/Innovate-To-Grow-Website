import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {UnsubscribeLoginPage} from '@/routes/UnsubscribeLoginPage/UnsubscribeLoginPage';

const unsubscribeMocks = vi.hoisted(() => ({
  unsubscribeAutoLogin: vi.fn(),
}));

vi.mock('@/features/auth', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth')>('@/features/auth');
  return {
    ...actual,
    unsubscribeAutoLogin: unsubscribeMocks.unsubscribeAutoLogin,
  };
});

const renderPage = (route: string) =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/unsubscribe-login" element={<UnsubscribeLoginPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('UnsubscribeLoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    unsubscribeMocks.unsubscribeAutoLogin.mockResolvedValue({message: 'ok'});
  });

  it('uses a token to unsubscribe and renders success', async () => {
    renderPage('/unsubscribe-login?token=abc');

    expect(screen.getByText('Unsubscribing you...')).toBeInTheDocument();
    expect(await screen.findByText('You have been unsubscribed from updates and announcements.')).toBeInTheDocument();
    expect(unsubscribeMocks.unsubscribeAutoLogin).toHaveBeenCalledWith('abc');
  });

  it('renders missing and invalid token errors', async () => {
    const missing = renderPage('/unsubscribe-login');
    expect(screen.getByText('No unsubscribe token provided.')).toBeInTheDocument();
    missing.unmount();

    unsubscribeMocks.unsubscribeAutoLogin.mockRejectedValueOnce(new Error('bad token'));
    renderPage('/unsubscribe-login?token=bad');
    expect(await screen.findByText('This unsubscribe link is invalid or has expired. Please update your email preferences manually.')).toBeInTheDocument();
  });
});
