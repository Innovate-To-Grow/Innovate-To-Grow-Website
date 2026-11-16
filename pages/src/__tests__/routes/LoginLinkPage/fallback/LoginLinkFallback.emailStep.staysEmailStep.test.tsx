import {cleanup, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
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

  describe('the email step', () => {
    it('stays on the email step, with the address kept, when sending the code fails', async () => {
      auth.requestLoginCode.mockRejectedValue(new Error('offline'));
      renderFallback();

      typeEmail('ada@example.com');
      submit();

      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      });
      expect(emailField()).toHaveValue('ada@example.com');
      expect(screen.queryByRole('textbox', {name: '6-digit verification code'})).toBeNull();
    });
  });
});
