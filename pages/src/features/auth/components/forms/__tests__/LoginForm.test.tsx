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

describe('LoginForm returnTo threading', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue({
      login: vi.fn(),
      requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'Code sent.'}),
      error: null,
      isLoading: false,
      clearError: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('forwards a safe returnTo to the email-code verification step', async () => {
    renderForm('/past-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue with Email'}));

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'login');
    });
    expect(mockNavigate).toHaveBeenCalledWith(
      '/verify-email?flow=auth&email=ada%40example.com&returnTo=%2Fpast-projects',
    );
  });

  it('omits the returnTo param from the verification step when none is supplied', async () => {
    renderForm();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue with Email'}));

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalled();
    });
    expect(mockNavigate).toHaveBeenCalledWith('/verify-email?flow=auth&email=ada%40example.com');
  });

  it('returns a password sign-in to the safe returnTo', async () => {
    renderForm('/past-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.login.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'hunter2!'}});
    fireEvent.click(screen.getByRole('button', {name: 'Sign In'}));

    await waitFor(() => {
      expect(authValue.login).toHaveBeenCalledWith('ada@example.com', 'hunter2!');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/past-projects', {replace: true});
  });
});
