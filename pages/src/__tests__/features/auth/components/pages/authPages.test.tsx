import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {ForgotPasswordPage} from '@/features/auth/components/pages/ForgotPasswordPage';
import {LoginPage} from '@/features/auth/components/pages/LoginPage';
import {RegisterPage} from '@/features/auth/components/pages/RegisterPage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/features/auth/components/forms/LoginForm', () => ({
  LoginForm: () => <form aria-label="Mock login form">Login form</form>,
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const setAuth = (overrides = {}) => {
  mockUseAuth.mockReturnValue({
    isAuthenticated: false,
    requiresProfileCompletion: false,
    requestPasswordReset: vi.fn().mockResolvedValue({message: 'Reset code sent.'}),
    error: null,
    isLoading: false,
    clearError: vi.fn(),
    ...overrides,
  });
};

describe('auth page wrappers', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    setAuth();
  });

  it('renders the login page for anonymous users and redirects authenticated users', () => {
    const {unmount} = render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/account" element={<div>Account route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Welcome to I2G'})).toBeInTheDocument();
    expect(screen.getByRole('form', {name: 'Mock login form'})).toBeInTheDocument();

    unmount();
    setAuth({isAuthenticated: true});

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/account" element={<div>Account route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Account route')).toBeInTheDocument();
  });

  it('redirects authenticated login users through complete-profile when required', () => {
    setAuth({isAuthenticated: true, requiresProfileCompletion: true});

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/complete-profile" element={<div>Profile route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Profile route')).toBeInTheDocument();
  });

  it('submits forgot-password requests and navigates to reset verification', async () => {
    render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <Routes>
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: ' ADA@Example.COM '}});
    expect(authValue.clearError).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Send Reset Code'}));

    await waitFor(() => {
      expect(authValue.requestPasswordReset).toHaveBeenCalledWith('ADA@Example.COM');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/verify-email?flow=reset&email=ada%40example.com', {replace: true});
  });

  it('renders forgot-password loading and error states and supports back navigation', () => {
    setAuth({isLoading: true, error: 'Reset failed'});

    render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <Routes>
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Reset failed');
    expect(screen.getByRole('button', {name: /sending code/i})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Back to login'}));
    expect(mockNavigate).toHaveBeenCalledWith('/login');
  });

  it('redirects authenticated forgot-password and legacy register routes', () => {
    setAuth({isAuthenticated: true, requiresProfileCompletion: true});

    const {unmount} = render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <Routes>
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/complete-profile" element={<div>Profile route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Profile route')).toBeInTheDocument();

    unmount();

    render(
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/login" element={<div>Login route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Login route')).toBeInTheDocument();
  });
});
