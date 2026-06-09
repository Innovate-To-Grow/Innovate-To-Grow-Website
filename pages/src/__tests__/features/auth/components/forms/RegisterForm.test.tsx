import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const navigateMock = vi.hoisted(() => vi.fn());
const authMock = vi.hoisted(() => ({
  register: vi.fn(),
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
    register: authMock.register,
    clearError: authMock.clearError,
    error: authMock.state.error,
    isLoading: authMock.state.isLoading,
  }),
}));

import {RegisterForm} from '@/features/auth/components/forms/RegisterForm';

const renderRegisterForm = () =>
  render(
    <MemoryRouter>
      <RegisterForm />
    </MemoryRouter>,
  );

describe('RegisterForm', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    authMock.state.error = null;
    authMock.state.isLoading = false;
  });

  it('creates an organization account and navigates to verification', async () => {
    authMock.register.mockResolvedValue({message: 'registered'});
    renderRegisterForm();

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: ' Ada '}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: ' Lovelace '}});
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'Member@Example.COM '}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: ' UC Merced '}});
    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: ' Director '}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'password123'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'password123'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);

    await waitFor(() =>
      expect(authMock.register).toHaveBeenCalledWith(
        'Member@Example.COM',
        'password123',
        'password123',
        'Ada',
        'Lovelace',
        'UC Merced',
        'Director',
      ),
    );
    expect(navigateMock).toHaveBeenCalledWith('/verify-email?flow=register&email=member%40example.com', {replace: true});
  });

  it('validates local fields and clears errors on edit', async () => {
    renderRegisterForm();

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Ada'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Lovelace'}});
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'bad-email'}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Org'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'short'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'different'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);

    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument();
    expect(screen.getByText('Password must be at least 8 characters')).toBeInTheDocument();
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
    expect(authMock.register).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'fixed@example.com'}});
    expect(authMock.clearError).toHaveBeenCalled();
  });

  it('creates an individual account without organization title fields', async () => {
    authMock.register.mockResolvedValue({message: 'registered'});
    renderRegisterForm();

    fireEvent.click(screen.getByRole('button', {name: /individual/i}));
    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Ada'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Lovelace'}});
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'password123'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'password123'}});
    fireEvent.click(screen.getByRole('button', {name: /create account/i}));

    await waitFor(() =>
      expect(authMock.register).toHaveBeenCalledWith(
        'ada@example.com',
        'password123',
        'password123',
        'Ada',
        'Lovelace',
        'Individual',
        '',
      ),
    );
  });

  it('renders backend errors and navigates to login from the switch link', () => {
    authMock.state.error = 'Registration failed';
    renderRegisterForm();

    expect(screen.getByText('Registration failed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /sign in/i}));
    expect(navigateMock).toHaveBeenCalledWith('/login');
  });
});
