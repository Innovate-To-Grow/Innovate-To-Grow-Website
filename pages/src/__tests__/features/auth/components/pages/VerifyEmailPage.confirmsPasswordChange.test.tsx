import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {enterCodeAndSubmit, renderPage} from '@/__tests__/features/auth/components/pages/verifyEmailPageFixtures';

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

  it('confirms a password change and navigates to /account', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=change&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
    authValue.confirmPasswordChange.mockResolvedValue({message: 'Password changed.'});

    enterCodeAndSubmit('Verify Code');
    await screen.findByText('Code verified. Set your new password below.');

    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'newpass123'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'newpass123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Change Password'}));

    await waitFor(() => {
      expect(authValue.confirmPasswordChange).toHaveBeenCalledWith('tok', 'newpass123', 'newpass123');
    });
    expect(await screen.findByText('Password changed.')).toBeInTheDocument();
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true}), {
      timeout: 2000,
    });
  });

  it('navigates back to /account from the change flow', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=change&email=ada@example.com');

    fireEvent.click(screen.getByRole('button', {name: 'Back to account'}));

    expect(mockNavigate).toHaveBeenCalledWith('/account');
  });

  it('navigates back to /forgot-password from the reset flow', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(mockNavigate).toHaveBeenCalledWith('/forgot-password');
  });

  it('navigates back to /login from the auth flow', async () => {
    renderPage('/verify-email?flow=auth&email=ada@example.com');

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(mockNavigate).toHaveBeenCalledWith('/login');
  });

  it.each(['auth', 'login', 'register', 'reset'])(
    'leaves focus alone on the standalone route (%s flow)',
    (flow) => {
      renderPage(`/verify-email?flow=${flow}&email=ada@example.com`);

      expect(screen.getByRole('textbox', {name: '6-digit verification code'})).not.toHaveFocus();
    },
  );
});
