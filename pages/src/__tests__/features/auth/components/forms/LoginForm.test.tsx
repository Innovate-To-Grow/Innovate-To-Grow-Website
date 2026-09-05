import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {LoginForm} from '@/features/auth/components/forms/LoginForm';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
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

describe('LoginForm unified email/phone field', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue({
      login: vi.fn(),
      requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'Code sent.'}),
      requestPhoneAuthCode: vi.fn().mockResolvedValue({message: 'Code sent.'}),
      error: null,
      isLoading: false,
      clearError: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('routes an email entry to the email-code step and threads returnTo', async () => {
    renderForm('/past-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'login');
    });
    expect(authValue.requestPhoneAuthCode).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith(
      '/verify-email?flow=auth&email=ada%40example.com&returnTo=%2Fpast-projects',
    );
  });

  it('omits returnTo from the verification step when none is supplied', async () => {
    renderForm();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalled();
    });
    expect(mockNavigate).toHaveBeenCalledWith('/verify-email?flow=auth&email=ada%40example.com');
  });

  it('disables Continue until the field holds a valid email or phone', () => {
    renderForm();
    const submit = screen.getByRole('button', {name: 'Continue'});
    const input = screen.getByLabelText('Email or phone number');

    expect(submit).toBeDisabled();

    fireEvent.change(input, {target: {value: 'not-an-identifier'}});
    expect(submit).toBeDisabled();

    fireEvent.change(input, {target: {value: 'ada@example.com'}});
    expect(submit).toBeEnabled();

    fireEvent.change(input, {target: {value: '2025550123'}});
    expect(submit).toBeEnabled();
  });

  it('returns a password sign-in to the safe returnTo', async () => {
    renderForm('/past-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.login.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'ada@example.com'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'hunter2!'}});
    fireEvent.click(screen.getByRole('button', {name: 'Sign In'}));

    await waitFor(() => {
      expect(authValue.login).toHaveBeenCalledWith('ada@example.com', 'hunter2!');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/past-projects', {replace: true});
  });

  it('signs in with a phone number and password', async () => {
    renderForm();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.login.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '(202) 555-0123'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'hunter2!'}});
    fireEvent.click(screen.getByRole('button', {name: 'Sign In'}));

    await waitFor(() => {
      expect(authValue.login).toHaveBeenCalledWith('2025550123', 'hunter2!');
    });
  });

  it('prefills the password email from a typed email when switching modes', () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));

    expect((screen.getByLabelText('Email or Phone') as HTMLInputElement).value).toBe('ada@example.com');
  });

  it('routes a phone entry to the phone-code step', async () => {
    renderForm();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: '2025550123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'login');
    });
    expect(authValue.requestEmailAuthCode).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/verify-phone?phone=2025550123');
  });

  it('shows a validation error for an invalid identifier submit', () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Email or phone number'), {target: {value: 'not-an-identifier'}});
    const form = screen.getByLabelText('Email or phone number').closest('form')!;
    fireEvent.submit(form);

    expect(screen.getByText('Please enter a valid email address or 10-digit US phone number.')).toBeInTheDocument();
  });

  it('shows a validation error for an empty password-mode identifier', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    const form = screen.getByLabelText('Email or Phone').closest('form')!;
    fireEvent.submit(form);

    expect(screen.getByText('Please enter your email or phone number.')).toBeInTheDocument();
  });

  it('shows a validation error for an invalid password-mode identifier', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'not-an-identifier'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'hunter2!'}});
    fireEvent.click(screen.getByRole('button', {name: 'Sign In'}));

    expect(screen.getByText('Please enter a valid email address or 10-digit US phone number.')).toBeInTheDocument();
  });

  it('shows a validation error for an empty password', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'ada@example.com'}});
    const form = screen.getByLabelText('Email or Phone').closest('form')!;
    fireEvent.submit(form);

    expect(screen.getByText('Please enter your password.')).toBeInTheDocument();
  });

  it('switches back to the identifier mode', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', {name: 'Sign in with password instead'}));
    fireEvent.click(screen.getByRole('button', {name: 'Sign in with a verification code'}));

    expect(screen.getByLabelText('Email or phone number')).toBeInTheDocument();
    expect(screen.queryByLabelText('Email or Phone')).not.toBeInTheDocument();
  });

  it('shows the context error when no validation error is present', () => {
    mockUseAuth.mockReturnValue({
      login: vi.fn(),
      requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'Code sent.'}),
      requestPhoneAuthCode: vi.fn().mockResolvedValue({message: 'Code sent.'}),
      error: 'Invalid credentials.',
      isLoading: false,
      clearError: vi.fn(),
    });
    renderForm();

    expect(screen.getByText('Invalid credentials.')).toBeInTheDocument();
  });
});
