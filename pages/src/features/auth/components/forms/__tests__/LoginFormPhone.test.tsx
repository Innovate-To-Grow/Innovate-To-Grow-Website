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

describe('LoginForm phone mode', () => {
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

  it('requests a phone code and navigates to verify-phone with national digits', async () => {
    renderForm('/past-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.click(screen.getByRole('button', {name: 'Use phone number instead'}));
    fireEvent.change(screen.getByLabelText('Phone number'), {target: {value: '(202) 555-0123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue with Phone'}));

    await waitFor(() => {
      expect(authValue.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'login');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/verify-phone?phone=2025550123&returnTo=%2Fpast-projects');
  });

  it('keeps submit disabled until a full 10-digit number is entered', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', {name: 'Use phone number instead'}));

    const submit = screen.getByRole('button', {name: 'Continue with Phone'});
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Phone number'), {target: {value: '202555'}});
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Phone number'), {target: {value: '2025550123'}});
    expect(submit).toBeEnabled();
  });

  it('can switch back to email mode', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', {name: 'Use phone number instead'}));
    expect(screen.getByLabelText('Phone number')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Use email instead'}));
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });
});
