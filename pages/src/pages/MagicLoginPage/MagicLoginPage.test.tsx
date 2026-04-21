import {render, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {MagicLoginPage} from './MagicLoginPage';

const mockMagicAutoLogin = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();

vi.mock('../../services/auth', () => ({
  magicAutoLogin: (...args: unknown[]) => mockMagicAutoLogin(...args),
}));

vi.mock('../../components/Auth/context/shared', () => ({
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('MagicLoginPage', () => {
  beforeEach(() => {
    mockMagicAutoLogin.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
  });

  it('navigates to the API-provided redirect when it is safe', async () => {
    mockMagicAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: '/schedule',
    });

    render(
      <MemoryRouter initialEntries={['/magic-login?token=abc123']}>
        <Routes>
          <Route path="/magic-login" element={<MagicLoginPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockMagicAutoLogin).toHaveBeenCalledWith('abc123');
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
  });

  it('falls back to /account when the API redirect is unsafe', async () => {
    mockMagicAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      redirect_to: 'https://evil.example',
    });

    render(
      <MemoryRouter initialEntries={['/magic-login?token=unsafe123']}>
        <Routes>
          <Route path="/magic-login" element={<MagicLoginPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockMagicAutoLogin).toHaveBeenCalledWith('unsafe123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('prefers complete-profile when the API says the account is incomplete', async () => {
    mockMagicAutoLogin.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    });

    render(
      <MemoryRouter initialEntries={['/magic-login?token=incomplete123']}>
        <Routes>
          <Route path="/magic-login" element={<MagicLoginPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockMagicAutoLogin).toHaveBeenCalledWith('incomplete123');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fschedule', {replace: true});
  });
});
