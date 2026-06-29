import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ForgotPasswordPage} from '../ForgotPasswordPage';

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

const renderPage = () =>
  render(
    <MemoryRouter>
      <ForgotPasswordPage />
    </MemoryRouter>,
  );

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      requiresProfileCompletion: false,
      requestPasswordReset: vi
        .fn()
        .mockResolvedValue({message: 'If an eligible account exists, a verification code has been sent.'}),
      error: null,
      isLoading: false,
      clearError: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('labels the identifier field "Email or Phone"', () => {
    renderPage();
    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();
  });

  it('requests a reset code for a phone number and routes to the reset verify step', async () => {
    renderPage();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '2025550123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send Reset Code'}));

    await waitFor(() => {
      expect(authValue.requestPasswordReset).toHaveBeenCalledWith('2025550123');
    });
    expect(mockNavigate).toHaveBeenCalledWith(expect.stringContaining('flow=reset'), {replace: true});
  });

  it('still accepts an email address (email-only flow preserved)', async () => {
    renderPage();
    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send Reset Code'}));

    await waitFor(() => {
      expect(authValue.requestPasswordReset).toHaveBeenCalledWith('ada@example.com');
    });
  });
});
