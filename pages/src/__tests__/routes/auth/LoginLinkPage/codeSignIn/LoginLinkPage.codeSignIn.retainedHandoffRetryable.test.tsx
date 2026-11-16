import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  expectFallback,
  handoffToken,
  httpError,
  NOTICE,
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

const LOGIN_RESPONSE = {
  message: 'Login successful.',
  access: 'access-token',
  refresh: 'refresh-token',
  user: {member_uuid: '123', email: 'ada@example.com'},
  redirect_to: '/schedule',
};

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

describe('LoginLinkPage — the code sign-in inside the fallback', () => {
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

  describe('the code sign-in inside the fallback', () => {
    const openCodeStep = async (email = 'ada@example.com') => {
      fireEvent.change(await screen.findByLabelText('Email address'), {target: {value: email}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
      await screen.findByRole('textbox', {name: '6-digit verification code'});
    };

    const typeCodeAndVerify = (auth: ReturnType<typeof buildAuth>, response: unknown) => {
      auth.verifyLoginCode.mockResolvedValue(response);
      fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {
        target: {value: '123456'},
      });
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
    };

    describe('the retained handoff of a retryable failure', () => {
      it('is dropped when the code step opens, yet Back then Retry still uses the token held in memory', async () => {
        mockLoginLinkAutoLogin
          .mockRejectedValueOnce(httpError(503))
          .mockResolvedValueOnce(LOGIN_RESPONSE);
        seedHandoff('flaky123');

        renderPage('/login-link');
        expect(await screen.findByRole('button', {name: RETRY})).toBeInTheDocument();
        expect(handoffToken()).toBe('flaky123');

        await openCodeStep();
        expect(handoffToken()).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Back'}));
        fireEvent.click(await screen.findByRole('button', {name: RETRY}));

        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
        });
        expect(mockLoginLinkAutoLogin).toHaveBeenNthCalledWith(2, 'flaky123');
      });

      it('cannot be replayed by a bare /login-link visit after the code sign-in', async () => {
        const auth = buildAuth();
        mockUseAuth.mockReturnValue(auth);
        mockLoginLinkAutoLogin.mockRejectedValue(httpError(503));
        seedHandoff('flaky123');

        const first = renderPage('/login-link');
        await openCodeStep();
        typeCodeAndVerify(auth, {next_step: 'account', requires_profile_completion: false});
        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
        });
        expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(1);
        first.unmount();

        // Later, in the same tab: nothing is left to submit.
        const {container} = renderPage('/login-link');

        expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
        expectFallback(container, NOTICE.unusable);
        expect(mockLoginLinkAutoLogin).toHaveBeenCalledTimes(1);
      });
    });
  });
});
