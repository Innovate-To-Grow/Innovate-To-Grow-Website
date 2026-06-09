import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {ImpersonateLoginPage} from '@/routes/ImpersonateLoginPage/ImpersonateLoginPage';

const impersonateMocks = vi.hoisted(() => ({
  dispatchAuthStateChange: vi.fn(),
  impersonateAutoLogin: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@/features/auth/api/session', () => ({
  impersonateAutoLogin: impersonateMocks.impersonateAutoLogin,
}));

vi.mock('@/features/auth/components/context/shared', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/components/context/shared')>('@/features/auth/components/context/shared');
  return {
    ...actual,
    dispatchAuthStateChange: impersonateMocks.dispatchAuthStateChange,
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => impersonateMocks.navigate,
  };
});

const renderPage = (route: string) =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/impersonate-login" element={<ImpersonateLoginPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('ImpersonateLoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    impersonateMocks.impersonateAutoLogin.mockResolvedValue({next_step: 'account'});
  });

  it('signs in with a token and navigates to the post-auth destination', async () => {
    renderPage('/impersonate-login?token=abc');

    expect(screen.getByText('Signing you in...')).toBeInTheDocument();
    await waitFor(() => expect(impersonateMocks.impersonateAutoLogin).toHaveBeenCalledWith('abc'));
    expect(impersonateMocks.dispatchAuthStateChange).toHaveBeenCalledTimes(1);
    expect(impersonateMocks.navigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('renders missing and invalid token errors', async () => {
    const missing = renderPage('/impersonate-login');
    expect(screen.getByText('No impersonation token provided.')).toBeInTheDocument();
    missing.unmount();

    impersonateMocks.impersonateAutoLogin.mockRejectedValueOnce(new Error('bad token'));
    renderPage('/impersonate-login?token=bad');
    expect(await screen.findByText('This impersonation link is invalid or has expired.')).toBeInTheDocument();
  });
});
