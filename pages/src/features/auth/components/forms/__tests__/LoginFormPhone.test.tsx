import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {LoginForm} from '../LoginForm';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const renderForm = (returnTo?: string | null) =>
  render(
    <MemoryRouter>
      <LoginForm returnTo={returnTo} />
    </MemoryRouter>,
  );

describe('LoginForm phone detection', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue({
      login: vi.fn(),
      requestEmailAuthCode: vi.fn(),
      requestPhoneAuthCode: vi.fn().mockResolvedValue({message: 'Code sent.'}),
      error: null,
      isLoading: false,
      clearError: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('detects a formatted phone number and routes to verify-phone with national digits', async () => {
    renderForm('/past-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: '(202) 555-0123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'login');
    });
    expect(authValue.requestEmailAuthCode).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/verify-phone?phone=2025550123&returnTo=%2Fpast-projects');
  });

  it('accepts a +1-prefixed number', async () => {
    renderForm();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: '+1 202 555 0123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'login');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/verify-phone?phone=2025550123');
  });

  it('can switch to password mode and back to the unified field', () => {
    renderForm();
    expect(screen.getByLabelText('Email or phone number')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    expect(screen.getByLabelText('Password')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Sign in with email code'}));
    expect(screen.getByLabelText('Email or phone number')).toBeInTheDocument();
  });
});
