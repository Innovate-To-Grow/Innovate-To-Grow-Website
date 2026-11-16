import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  codeField,
  codeHeading,
  GENERIC_ACK,
  handoffToken,
  renderFallback,
  seedHandoff,
  submit,
  typeEmail,
} from '@/__tests__/routes/auth/LoginLinkPage/fallback/loginLinkFallbackFixtures';

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

  describe('the retained link handoff', () => {
    // A retryable failure (429, 5xx, network) keeps the token in sessionStorage
    // so Retry or a reload can try again. Once the visitor signs in another way
    // it must not linger: a later bare /login-link in this tab would re-submit
    // it and swap the session they just established.
    it('is kept while the code has not been requested, and when requesting it fails', async () => {
      seedHandoff('flaky123');
      auth.requestLoginCode.mockRejectedValue(new Error('offline'));
      renderFallback({kind: 'unavailable', onRetry: vi.fn()});
      expect(handoffToken()).toBe('flaky123');

      typeEmail('ada@example.com');
      submit();
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      });

      expect(screen.queryByRole('textbox', {name: '6-digit verification code'})).toBeNull();
      expect(handoffToken()).toBe('flaky123');
    });

    it('is not dropped while the code request is still in flight, only once it has succeeded', async () => {
      seedHandoff('flaky123');
      let accept!: (value: {message: string}) => void;
      auth.requestLoginCode.mockReturnValue(
        new Promise((resolve) => {
          accept = resolve;
        }),
      );
      renderFallback({kind: 'unavailable', onRetry: vi.fn()});

      typeEmail('ada@example.com');
      submit();
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      });
      expect(handoffToken()).toBe('flaky123');

      accept({message: GENERIC_ACK});
      await codeHeading();
      expect(handoffToken()).toBeNull();
    });

    it.each<[string, string | null]>([
      ['a link destination', '/schedule'],
      ['no link destination', null],
    ])('is dropped again when the code signs the visitor in (%s)', async (_label, returnTo) => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      renderFallback({kind: 'unavailable', returnTo, onRetry: vi.fn()});
      typeEmail('ada@example.com');
      submit();
      await codeHeading();
      // Whatever put a token back in the meantime is gone once the visitor is in.
      seedHandoff('reappeared123');
      expect(handoffToken()).toBe('reappeared123');

      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(returnTo ?? '/account', {replace: true});
      });
      expect(handoffToken()).toBeNull();
    });

    it('is kept when the code is wrong', async () => {
      auth.verifyLoginCode.mockRejectedValue(new Error('Invalid or expired code.'));
      renderFallback();
      typeEmail('ada@example.com');
      submit();
      await codeHeading();
      seedHandoff('reappeared123');

      fireEvent.change(codeField(), {target: {value: '000000'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });

      expect(handoffToken()).toBe('reappeared123');
    });
  });
});
