import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {VerifyEmailPage} from '../VerifyEmailPage';

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

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();

    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      requiresProfileCompletion: false,
      error: null,
      isLoading: false,
      requestEmailAuthCode: vi.fn(),
      verifyEmailAuthCode: vi.fn(),
      clearError: vi.fn(),
      verifyLoginCode: vi.fn(),
      verifyRegistrationCode: vi.fn().mockResolvedValue({message: 'ok'}),
      resendRegistrationCode: vi.fn(),
      requestLoginCode: vi.fn(),
      requestPasswordReset: vi.fn(),
      verifyPasswordResetCode: vi.fn(),
      confirmPasswordReset: vi.fn(),
      requestPasswordChangeCode: vi.fn(),
      verifyPasswordChangeCode: vi.fn(),
      confirmPasswordChange: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('returns to /subscribe after register verification when returnTo is safe', async () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=register&email=ada@example.com&returnTo=%2Fsubscribe']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '123456'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Activate'}));

    await waitFor(() => {
      expect(authValue.verifyRegistrationCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/subscribe', {replace: true});
  });

  it('returns to a safe returnTo after auth-code verification', async () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=auth&email=ada@example.com&returnTo=%2Fpast-projects']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyEmailAuthCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '123456'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/past-projects', {replace: true});
  });

  it('ignores an unsafe returnTo on the auth flow and uses the default destination', async () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=auth&email=ada@example.com&returnTo=https%3A%2F%2Fevil.example']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyEmailAuthCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '123456'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('resends auth codes through the email-auth endpoint with the login source', async () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=auth&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestEmailAuthCode.mockResolvedValue({message: 'Code resent.'});

    const resendButtons = screen.getAllByRole('button', {name: 'Resend code'});
    fireEvent.click(resendButtons.at(-1)!);

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'login');
    });

    expect(await screen.findByText('Code resent.')).toBeInTheDocument();
  });
});
