import {cleanup, fireEvent, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {type LoginLinkFallbackKind} from '@/routes/LoginLinkPage/LoginLinkFallback';
import {
  GENERIC_ACK,
  INSTEAD,
  renderFallback,
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

  describe('the notice', () => {
    it.each<[LoginLinkFallbackKind, string]>([
      ['expired', 'This sign-in link has expired.'],
      ['already_used', 'This sign-in link has already been used.'],
      ['rate_limited', "We couldn't verify your sign-in link right now."],
      ['unavailable', "We couldn't verify your sign-in link right now."],
      ['invalid', "This sign-in link can't be used."],
    ])('for %s leads with its own sentence, then the code offer', (kind, sentence) => {
      renderFallback({kind});

      const notice = screen.getByRole('status');
      expect(notice).toHaveClass('auth-alert', 'info');
      expect(notice.textContent).toBe(`${sentence} ${INSTEAD}`);
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('is informational, in the same page layout as the login page', () => {
      const {container} = renderFallback();

      // Title on the page, notice and form in the panel below it (no logo: the site header carries it).
      expect(container.querySelector('.auth-page > .auth-page-header h1')).not.toBeNull();
      expect(container.querySelector('.auth-page > .auth-page-card .auth-alert.info')).not.toBeNull();
      expect(container.querySelector('.auth-page img')).toBeNull();
      expect(screen.getByRole('heading', {name: 'Sign in to I2G', level: 1})).toBeInTheDocument();
      expect(container.querySelector('.magic-login-error')).toBeNull();
      expect(container.querySelector('.auth-alert.error')).toBeNull();
    });
  });

  describe('the retry control', () => {
    it('is absent unless retrying can help', () => {
      renderFallback({kind: 'expired'});

      expect(screen.queryByRole('button', {name: 'Try the link again'})).toBeNull();
    });

    it('calls onRetry', () => {
      const onRetry = vi.fn();
      renderFallback({kind: 'unavailable', onRetry});

      fireEvent.click(screen.getByRole('button', {name: 'Try the link again'}));

      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('is disabled while a code is being sent', () => {
      mockUseAuth.mockReturnValue(buildAuth({isLoading: true}));
      renderFallback({kind: 'unavailable', onRetry: vi.fn()});

      expect(screen.getByRole('button', {name: 'Try the link again'})).toBeDisabled();
    });
  });
});
