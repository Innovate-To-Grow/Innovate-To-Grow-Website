import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  codeField,
  codeHeading,
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

  describe('the existing-accounts code flow', () => {
    // The unified email-auth flow creates a pending account for an address it
    // does not know, so a typo here would sign the visitor in as a stranger. A
    // login link only ever exists for an existing member.
    it('never touches the unified email-auth flow, from the request to the sign-in', async () => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      renderFallback();
      typeEmail('nobody@example.com');
      submit();
      await codeHeading();

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(2);
      });
      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });

      expect(auth.requestEmailAuthCode).not.toHaveBeenCalled();
      expect(auth.verifyEmailAuthCode).not.toHaveBeenCalled();
    });

    it('never touches the unified flow when the request fails or the code is wrong either', async () => {
      auth.requestLoginCode.mockRejectedValueOnce(new Error('offline'));
      auth.verifyLoginCode.mockRejectedValue(new Error('Invalid or expired code.'));
      renderFallback();
      typeEmail('ada@example.com');
      submit();
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      });
      submit();
      await codeHeading();
      fireEvent.change(codeField(), {target: {value: '000000'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });

      expect(auth.requestEmailAuthCode).not.toHaveBeenCalled();
      expect(auth.verifyEmailAuthCode).not.toHaveBeenCalled();
    });
  });
});
