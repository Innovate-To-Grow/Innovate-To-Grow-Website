import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  codeField,
  codeHeading,
  emailField,
  GENERIC_ACK,
  renderFallback,
  submit,
  typeEmail,
} from '@/__tests__/routes/LoginLinkPage/fallback/loginLinkFallbackFixtures';

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
  // The unified flow creates a pending account for an address it does not know;
  // the fallback must never reach it.
  requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'Check your email for a verification code.'}),
  verifyEmailAuthCode: vi.fn(),
  clearError: vi.fn(),
  verifyLoginCode: vi.fn(),
  verifyRegistrationCode: vi.fn(),
  resendRegistrationCode: vi.fn(),
  requestLoginCode: vi.fn().mockResolvedValue({message: GENERIC_ACK}),
  requestPasswordReset: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  confirmPasswordReset: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  verifyPasswordChangeCode: vi.fn(),
  confirmPasswordChange: vi.fn(),
  ...overrides,
});

describe('LoginLinkFallback', () => {
  let auth: ReturnType<typeof buildAuth>;

  beforeEach(() => {
    mockNavigate.mockReset();
    mockUseAuth.mockReset();
    auth = buildAuth();
    mockUseAuth.mockReturnValue(auth);
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    cleanup();
  });

  describe('the code step', () => {
    const openCodeStep = async (returnTo: string | null = null) => {
      renderFallback({returnTo});
      typeEmail('ada@example.com');
      submit();
      await codeHeading();
    };

    it('puts focus on the code field when it opens, not on <body>', async () => {
      await openCodeStep();

      expect(codeField()).toHaveFocus();
    });

    it('verifies the code through the login flow and continues to the link destination', async () => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      await openCodeStep('/schedule');

      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledWith('ada@example.com', '123456');
      });
      expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
    });

    it('continues to /account when the link had no destination', async () => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      await openCodeStep(null);

      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
    });

    it('keeps the visitor on the code step when the code is wrong', async () => {
      auth.verifyLoginCode.mockRejectedValue(new Error('Invalid or expired code.'));
      await openCodeStep('/schedule');

      fireEvent.change(codeField(), {target: {value: '000000'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(codeField()).toBeInTheDocument();
    });

    it('resends the code through the same login request', async () => {
      await openCodeStep();
      auth.requestLoginCode.mockClear();
      auth.requestLoginCode.mockResolvedValue({message: 'A new code is on its way.'});

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
      });
      expect(await screen.findByText('A new code is on its way.')).toBeInTheDocument();
      // Still on the code step.
      expect(codeField()).toBeInTheDocument();
    });

    it('goes back to the email step, inline, with the address kept and errors cleared', async () => {
      await openCodeStep();
      auth.clearError.mockClear();

      fireEvent.click(screen.getByRole('button', {name: 'Back'}));

      expect(await screen.findByLabelText('Email address')).toHaveValue('ada@example.com');
      await waitFor(() => expect(emailField()).toHaveFocus());
      expect(auth.clearError).toHaveBeenCalled();
      // The default Back leaves for /login, which would strand a signed-in browser.
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('can send a code to a corrected address after going back', async () => {
      await openCodeStep();
      fireEvent.click(screen.getByRole('button', {name: 'Back'}));
      typeEmail('grace@example.com');
      auth.requestLoginCode.mockClear();
      submit();

      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledWith('grace@example.com');
      });
      expect(await screen.findByText('grace@example.com')).toBeInTheDocument();
      // Focus follows every arrival at the code step, not just the first.
      expect(codeField()).toHaveFocus();
    });
  });
});
