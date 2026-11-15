import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {VerifyEmailPageContent} from '@/features/auth/components/pages/VerifyEmailPage';
import type {VerifyFlow} from '@/features/auth/components/pages/verify/shared';
import {enterCodeAndSubmit} from '@/__tests__/features/auth/components/pages/verifyEmailPageFixtures';

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

describe('VerifyEmailPageContent', () => {
  const renderContent = (
    onBack?: () => void,
    props: {flow?: VerifyFlow; onSignedIn?: () => void; autoFocus?: boolean} = {},
  ) =>
    render(
      <MemoryRouter>
        <VerifyEmailPageContent
          flow={props.flow ?? 'auth'}
          email="ada@example.com"
          returnTo="/schedule"
          onBack={onBack}
          onSignedIn={props.onSignedIn}
          autoFocus={props.autoFocus}
        />
      </MemoryRouter>,
    );

  const codeField = () => screen.getByRole('textbox', {name: '6-digit verification code'});

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue(buildAuth());
  });

  afterEach(() => {
    cleanup();
  });

  it('runs a supplied onBack instead of navigating away', () => {
    const onBack = vi.fn();
    renderContent(onBack);

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('keeps the flow default when no onBack is supplied', () => {
    renderContent();

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(mockNavigate).toHaveBeenCalledWith('/login');
  });

  it('verifies the code and honours the given returnTo without a route of its own', async () => {
    const auth = buildAuth();
    auth.verifyEmailAuthCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
    mockUseAuth.mockReturnValue(auth);
    renderContent(vi.fn());

    enterCodeAndSubmit('Continue');

    await waitFor(() => {
      expect(auth.verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
  });

  describe('focus', () => {
    it('does not focus the code field unless asked to', () => {
      renderContent();

      expect(codeField()).not.toHaveFocus();
    });

    it.each(['auth', 'login'] as const)('focuses the code field on mount when asked to (%s flow)', (flow) => {
      renderContent(undefined, {flow, autoFocus: true});

      expect(codeField()).toHaveFocus();
    });

    it('does not steal focus for the password form that replaces the code field', async () => {
      const auth = buildAuth();
      auth.verifyPasswordResetCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
      mockUseAuth.mockReturnValue(auth);
      renderContent(undefined, {flow: 'reset', autoFocus: true});
      expect(codeField()).toHaveFocus();

      enterCodeAndSubmit('Verify Code');

      expect(await screen.findByLabelText('New Password')).not.toHaveFocus();
    });
  });

  describe('onSignedIn', () => {
    const SIGN_IN: Array<[VerifyFlow, string, 'verifyEmailAuthCode' | 'verifyLoginCode' | 'verifyRegistrationCode']> = [
      ['auth', 'Continue', 'verifyEmailAuthCode'],
      ['login', 'Verify and Sign In', 'verifyLoginCode'],
      ['register', 'Verify and Activate', 'verifyRegistrationCode'],
    ];

    it.each(SIGN_IN)('runs after a %s code signs the visitor in, before navigating on', async (flow, button, method) => {
      const auth = buildAuth();
      auth[method].mockResolvedValue({
        next_step: 'account',
        requires_profile_completion: false,
      });
      mockUseAuth.mockReturnValue(auth);
      const order: string[] = [];
      const onSignedIn = vi.fn(() => order.push('signed-in'));
      mockNavigate.mockImplementation(() => order.push('navigate'));
      renderContent(undefined, {flow, onSignedIn});

      enterCodeAndSubmit(button);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledTimes(1);
      });
      expect(onSignedIn).toHaveBeenCalledTimes(1);
      expect(order).toEqual(['signed-in', 'navigate']);
    });

    it.each(SIGN_IN)('does not run when the %s code is rejected', async (flow, button, method) => {
      const auth = buildAuth();
      auth[method].mockRejectedValue(new Error('Invalid code.'));
      mockUseAuth.mockReturnValue(auth);
      const onSignedIn = vi.fn();
      renderContent(undefined, {flow, onSignedIn});

      enterCodeAndSubmit(button);

      await waitFor(() => {
        expect(auth[method]).toHaveBeenCalledTimes(1);
      });
      expect(onSignedIn).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('does not run for a flow that does not sign anyone in', async () => {
      const auth = buildAuth();
      auth.verifyPasswordResetCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
      mockUseAuth.mockReturnValue(auth);
      const onSignedIn = vi.fn();
      renderContent(undefined, {flow: 'reset', onSignedIn});

      enterCodeAndSubmit('Verify Code');

      expect(await screen.findByLabelText('New Password')).toBeInTheDocument();
      expect(onSignedIn).not.toHaveBeenCalled();
    });
  });
});
