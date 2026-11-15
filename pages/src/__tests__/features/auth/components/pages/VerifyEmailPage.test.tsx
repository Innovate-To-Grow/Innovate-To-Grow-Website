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

  it('returns to /subscribe after register verification when returnTo is safe', async () => {
    renderPage('/verify-email?flow=register&email=ada@example.com&returnTo=%2Fsubscribe');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    enterCodeAndSubmit('Verify and Activate');

    await waitFor(() => {
      expect(authValue.verifyRegistrationCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/subscribe', {replace: true});
  });

  it('returns to a safe returnTo after auth-code verification', async () => {
    renderPage('/verify-email?flow=auth&email=ada@example.com&returnTo=%2Fpast-projects');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyEmailAuthCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    enterCodeAndSubmit('Continue');

    await waitFor(() => {
      expect(authValue.verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/past-projects', {replace: true});
  });

  it('ignores an unsafe returnTo on the auth flow and uses the default destination', async () => {
    renderPage('/verify-email?flow=auth&email=ada@example.com&returnTo=https%3A%2F%2Fevil.example');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyEmailAuthCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    enterCodeAndSubmit('Continue');

    await waitFor(() => {
      expect(authValue.verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('resends auth codes through the email-auth endpoint with the login source', async () => {
    renderPage('/verify-email?flow=auth&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestEmailAuthCode.mockResolvedValue({message: 'Code resent.'});

    const resendButtons = screen.getAllByRole('button', {name: 'Resend code'});
    fireEvent.click(resendButtons.at(-1)!);

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'login');
    });

    expect(await screen.findByText('Code resent.')).toBeInTheDocument();
  });

  it('redirects to /login for an unknown flow', async () => {
    renderPage('/verify-email?flow=bogus&email=ada@example.com');

    expect(await screen.findByText('login-route')).toBeInTheDocument();
  });

  it('redirects to /login when the email is missing', async () => {
    renderPage('/verify-email?flow=auth');

    expect(await screen.findByText('login-route')).toBeInTheDocument();
  });

  it('redirects to /login for an unauthenticated change flow', async () => {
    renderPage('/verify-email?flow=change&email=ada@example.com');

    expect(await screen.findByText('login-route')).toBeInTheDocument();
  });

  it('redirects an authenticated auth flow to its returnTo', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=auth&email=ada@example.com&returnTo=%2Fpast-projects');

    expect(await screen.findByText('past-projects-route')).toBeInTheDocument();
  });

  it('redirects an authenticated login flow without returnTo to /account', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=login&email=ada@example.com');

    expect(await screen.findByText('account-route')).toBeInTheDocument();
  });

  it('redirects an authenticated register flow to /complete-profile when completion is required', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true, requiresProfileCompletion: true}));
    renderPage('/verify-email?flow=register&email=ada@example.com');

    expect(await screen.findByText('complete-profile-route')).toBeInTheDocument();
  });

  it('verifies a login code', async () => {
    renderPage('/verify-email?flow=login&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyLoginCode.mockResolvedValue({
      next_step: 'account',
      requires_profile_completion: false,
      redirect_to: '/account',
    });

    enterCodeAndSubmit('Verify and Sign In');

    await waitFor(() => {
      expect(authValue.verifyLoginCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('detours a register verification through profile completion', async () => {
    renderPage('/verify-email?flow=register&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyRegistrationCode.mockResolvedValue({
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });

    enterCodeAndSubmit('Verify and Activate');

    await waitFor(() => {
      expect(authValue.verifyRegistrationCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile', {replace: true});
  });
});
