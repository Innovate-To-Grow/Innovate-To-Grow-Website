import {cleanup, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  SessionNotSavedError,
} from '@/features/auth/api/contracts/errors';
import {
  handoffToken,
  renderPage,
  RETRY,
  seedHandoff,
  STORED_SESSION,
} from '@/__tests__/routes/auth/LoginLinkPage/fixtures/loginLinkPageFixtures';

const mockLoginLinkAutoLogin = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();
const mockGetAccessToken = vi.fn();
const mockBootstrapAuthSession = vi.fn();
const mockUseAuth = vi.fn();

vi.mock('@/features/auth/api/signin/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/signin/session')>()),
  loginLinkAutoLogin: (...args: unknown[]) => mockLoginLinkAutoLogin(...args),
  bootstrapAuthSession: () => mockBootstrapAuthSession(),
}));

vi.mock('@/features/auth/api/session/storage', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/session/storage')>()),
  getAccessToken: () => mockGetAccessToken(),
}));

vi.mock('@/features/auth/components/context/shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/components/context/shared')>()),
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

// The fallback's own behaviour is covered in LoginLinkFallback.test.tsx and, end
// to end with the real provider, in LoginLinkPage.integration.test.tsx.
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

const NOT_SAVED = 'Your browser blocked saving your login session. Please log in manually.';

const buildAuth = (overrides: Record<string, unknown> = {}) => ({
  isAuthenticated: false,
  requiresProfileCompletion: false,
  error: null,
  isLoading: false,
  // The unified flow creates an account for an unknown address; it must stay unused.
  requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'Check your email for a verification code.'}),
  verifyEmailAuthCode: vi.fn(),
  clearError: vi.fn(),
  verifyLoginCode: vi.fn(),
  verifyRegistrationCode: vi.fn(),
  resendRegistrationCode: vi.fn(),
  requestLoginCode: vi
    .fn()
    .mockResolvedValue({message: 'If an eligible account exists, a verification code has been sent.'}),
  requestPasswordReset: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  confirmPasswordReset: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  verifyPasswordChangeCode: vi.fn(),
  confirmPasswordChange: vi.fn(),
  ...overrides,
});

describe('LoginLinkPage — failures during and after the exchange', () => {
  beforeEach(() => {
    mockLoginLinkAutoLogin.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
    mockGetAccessToken.mockReset();
    mockGetAccessToken.mockReturnValue(null);
    mockBootstrapAuthSession.mockReset();
    mockBootstrapAuthSession.mockResolvedValue({status: 'verified', session: STORED_SESSION});
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(buildAuth());
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    cleanup();
  });

  describe('a session that could not be saved', () => {
    it('explains the blocked storage, keeps the plain error, and offers no fallback or retry', async () => {
      mockLoginLinkAutoLogin.mockRejectedValue(new SessionNotSavedError());
      // A stale session from another account must not hide the failure.
      mockGetAccessToken.mockReturnValue('stale-access-token');
      seedHandoff('spent123');

      const {container} = renderPage('/login-link');

      expect(await screen.findByText(NOT_SAVED)).toBeInTheDocument();
      expect(container.querySelector('.magic-login-error')).toHaveTextContent(NOT_SAVED);
      expect(screen.getByRole('link', {name: 'Go to Login'})).toHaveAttribute('href', '/login');
      // The code sign-in could not persist a session either.
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(screen.queryByRole('status')).toBeNull();
      expect(screen.queryByRole('button', {name: RETRY})).toBeNull();
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
      // The token was consumed by the server, so nothing is worth keeping.
      expect(handoffToken()).toBeNull();
    });
  });
});
