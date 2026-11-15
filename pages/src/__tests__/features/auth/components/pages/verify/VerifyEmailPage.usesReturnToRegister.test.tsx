import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {enterCodeAndSubmit, renderPage} from '@/__tests__/features/auth/components/pages/verify/verifyEmailPageFixtures';

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

const buildAuth = (overrides: Record<string, unknown> = {}) => ({
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
  ...overrides,
});

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue(buildAuth());
  });

  afterEach(() => {
    cleanup();
  });

  it('uses returnTo for a register verification that does not need completion', async () => {
    renderPage('/verify-email?flow=register&email=ada@example.com&returnTo=%2Fevent-registration');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyRegistrationCode.mockResolvedValue({
      next_step: 'account',
      requires_profile_completion: false,
    });

    enterCodeAndSubmit('Verify and Activate');

    await waitFor(() => {
      expect(authValue.verifyRegistrationCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/event-registration', {replace: true});
  });

  it('verifies a reset code and opens the password form', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordResetCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});

    enterCodeAndSubmit('Verify Code');

    await waitFor(() => {
      expect(authValue.verifyPasswordResetCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(await screen.findByText('Code verified. Set your new password below.')).toBeInTheDocument();
    expect(screen.getByLabelText('New Password')).toBeInTheDocument();
  });

  it('verifies a change code and opens the password form', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=change&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});

    enterCodeAndSubmit('Verify Code');

    await waitFor(() => {
      expect(authValue.verifyPasswordChangeCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(await screen.findByText('Code verified. Set your new password below.')).toBeInTheDocument();
  });

  it('resends a login code', async () => {
    renderPage('/verify-email?flow=login&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestLoginCode.mockResolvedValue({message: 'Login code resent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Login code resent.')).toBeInTheDocument();
  });

  it('resends a registration code', async () => {
    renderPage('/verify-email?flow=register&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.resendRegistrationCode.mockResolvedValue({message: 'Registration code resent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.resendRegistrationCode).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Registration code resent.')).toBeInTheDocument();
  });

  it('resends a password reset code', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestPasswordReset.mockResolvedValue({message: 'Reset code sent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.requestPasswordReset).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Reset code sent.')).toBeInTheDocument();
  });

  it('resends a password change code', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=change&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestPasswordChangeCode.mockResolvedValue({message: 'Change code sent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.requestPasswordChangeCode).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Change code sent.')).toBeInTheDocument();
  });

  it('confirms a password reset and navigates to /login', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordResetCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
    authValue.confirmPasswordReset.mockResolvedValue({message: 'Password reset.'});

    enterCodeAndSubmit('Verify Code');
    await screen.findByText('Code verified. Set your new password below.');

    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'newpass123'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'newpass123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Reset Password'}));

    await waitFor(() => {
      expect(authValue.confirmPasswordReset).toHaveBeenCalledWith(
        'ada@example.com',
        'tok',
        'newpass123',
        'newpass123',
      );
    });
    expect(await screen.findByText('Password reset.')).toBeInTheDocument();
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/login', {replace: true}), {
      timeout: 2000,
    });
  });
});
