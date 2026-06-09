import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const navigateMock = vi.hoisted(() => vi.fn());
const authMock = vi.hoisted(() => ({
  login: vi.fn(),
  requestEmailAuthCode: vi.fn(),
  clearError: vi.fn(),
  state: {
    error: null as string | null,
    isLoading: false,
  },
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => ({
    login: authMock.login,
    requestEmailAuthCode: authMock.requestEmailAuthCode,
    clearError: authMock.clearError,
    error: authMock.state.error,
    isLoading: authMock.state.isLoading,
  }),
}));

import {LoginForm} from '@/features/auth/components/forms/LoginForm';

const renderLoginForm = () =>
  render(
    <MemoryRouter>
      <LoginForm />
    </MemoryRouter>,
  );

describe('LoginForm', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    authMock.state.error = null;
    authMock.state.isLoading = false;
  });

  it('validates email-code login and navigates to verification on success', async () => {
    authMock.requestEmailAuthCode.mockResolvedValue({message: 'Code sent'});
    renderLoginForm();

    fireEvent.submit(screen.getByRole('button', {name: /continue with email/i}).closest('form')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Please enter your email address.');

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'Member@Example.COM '}});
    fireEvent.click(screen.getByRole('button', {name: /continue with email/i}));

    await waitFor(() => expect(authMock.requestEmailAuthCode).toHaveBeenCalledWith('Member@Example.COM', 'login'));
    expect(navigateMock).toHaveBeenCalledWith('/verify-email?flow=auth&email=member%40example.com');
  });

  it('switches to password login and redirects using the post-auth response', async () => {
    authMock.login.mockResolvedValue({user: {email: 'member@example.com'}, redirect_to: '/account'});
    renderLoginForm();

    fireEvent.click(screen.getByRole('button', {name: /sign in with password instead/i}));
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Please enter your email address.');

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'member@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Please enter your password.');

    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'secret-password'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);

    await waitFor(() => expect(authMock.login).toHaveBeenCalledWith('member@example.com', 'secret-password'));
    expect(navigateMock).toHaveBeenCalledWith('/account', {replace: true});

    fireEvent.click(screen.getByRole('button', {name: /sign in with email code/i}));
    expect(screen.getByRole('button', {name: /continue with email/i})).toBeInTheDocument();
  });

  it('renders context errors', () => {
    authMock.state.error = 'Backend rejected login';

    renderLoginForm();

    expect(screen.getByRole('alert')).toHaveTextContent('Backend rejected login');
  });
});
