import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {VerifyEmailPage, VerifyEmailPageContent} from '@/features/auth/components/pages/VerifyEmailPage';
import type {VerifyFlow} from '@/features/auth/components/pages/verify/shared';

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

const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/login" element={<div>login-route</div>} />
        <Route path="/account" element={<div>account-route</div>} />
        <Route path="/complete-profile" element={<div>complete-profile-route</div>} />
        <Route path="/forgot-password" element={<div>forgot-password-route</div>} />
        <Route path="/past-projects" element={<div>past-projects-route</div>} />
        <Route path="/event-registration" element={<div>event-registration-route</div>} />
      </Routes>
    </MemoryRouter>,
  );

const enterCodeAndSubmit = (buttonName: string) => {
  fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {
    target: {value: '123456'},
  });
  fireEvent.click(screen.getByRole('button', {name: buttonName}));
};

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

  it('uses returnTo for a register verification that does not need completion', async () => {
    renderPage('/verify-email?flow=register&email=ada@example.com&returnTo=%2Fevent-registration');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyRegistrationCode.mockResolvedValue({
      next_step: 'account',
      requires_profile_completion: false,
    });

    enterCodeAndSubmit('Verify and Activate');

    await waitFor(() => {
      expect(authValue.verifyRegistrationCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/event-registration', {replace: true});
  });

  it('verifies a reset code and opens the password form', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordResetCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});

    enterCodeAndSubmit('Verify Code');

    await waitFor(() => {
      expect(authValue.verifyPasswordResetCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(await screen.findByText('Code verified. Set your new password below.')).toBeInTheDocument();
    expect(screen.getByLabelText('New Password')).toBeInTheDocument();
  });

  it('verifies a change code and opens the password form', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=change&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});

    enterCodeAndSubmit('Verify Code');

    await waitFor(() => {
      expect(authValue.verifyPasswordChangeCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });
    expect(await screen.findByText('Code verified. Set your new password below.')).toBeInTheDocument();
  });

  it('resends a login code', async () => {
    renderPage('/verify-email?flow=login&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestLoginCode.mockResolvedValue({message: 'Login code resent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Login code resent.')).toBeInTheDocument();
  });

  it('resends a registration code', async () => {
    renderPage('/verify-email?flow=register&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.resendRegistrationCode.mockResolvedValue({message: 'Registration code resent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.resendRegistrationCode).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Registration code resent.')).toBeInTheDocument();
  });

  it('resends a password reset code', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestPasswordReset.mockResolvedValue({message: 'Reset code sent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.requestPasswordReset).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Reset code sent.')).toBeInTheDocument();
  });

  it('resends a password change code', async () => {
    mockUseAuth.mockReturnValue(buildAuth({isAuthenticated: true}));
    renderPage('/verify-email?flow=change&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestPasswordChangeCode.mockResolvedValue({message: 'Change code sent.'});

    fireEvent.click(screen.getAllByRole('button', {name: 'Resend code'}).at(-1)!);

    await waitFor(() => {
      expect(authValue.requestPasswordChangeCode).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText('Change code sent.')).toBeInTheDocument();
  });

  it('confirms a password reset and navigates to /login', async () => {
    renderPage('/verify-email?flow=reset&email=ada@example.com');

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPasswordResetCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
    authValue.confirmPasswordReset.mockResolvedValue({message: 'Password reset.'});

    enterCodeAndSubmit('Verify Code');
    await screen.findByText('Code verified. Set your new password below.');

    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'newpass123'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'newpass123'}});
    fireEvent.click(screen.getByRole('button', {name: 'Reset Password'}));

    await waitFor(() => {
      expect(authValue.confirmPasswordReset).toHaveBeenCalledWith(
        'ada@example.com',
        'tok',
        'newpass123',
        'newpass123',
      );
    });
    expect(await screen.findByText('Password reset.')).toBeInTheDocument();
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/login', {replace: true}), {
      timeout: 2000,
    });
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

describe('VerifyEmailPageContent message and hint', () => {
  const ACK = 'If an eligible account exists, a verification code has been sent.';
  const HINT = "Didn't get a code? Check the address above or go back to correct it.";

  const renderContent = (props: {initialMessage?: string | null; hint?: string | null} = {}) =>
    render(
      <MemoryRouter>
        <VerifyEmailPageContent flow="login" email="ada@example.com" returnTo={null} {...props} />
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

  it('shows no message, hint, or description by default', () => {
    const {container} = renderContent();

    expect(screen.queryByRole('status')).toBeNull();
    expect(container.querySelector('.auth-help-text')).toBeNull();
    expect(codeField()).not.toHaveAttribute('aria-describedby');
  });

  it('is unchanged on the standalone /verify-email route', () => {
    const {container} = renderPage('/verify-email?flow=login&email=ada@example.com');

    expect(screen.queryByRole('status')).toBeNull();
    expect(container.querySelector('.auth-help-text')).toBeNull();
    expect(codeField()).not.toHaveAttribute('aria-describedby');
  });

  it('opens with the initial message as an info status', () => {
    renderContent({initialMessage: ACK});

    const status = screen.getByRole('status');
    expect(status).toHaveClass('auth-alert', 'info');
    expect(status).toHaveTextContent(ACK);
    // The address block above it is still there, once.
    expect(screen.getAllByText('ada@example.com')).toHaveLength(1);
  });

  it('shows the hint as help text under the code field', () => {
    const {container} = renderContent({hint: HINT});

    const help = screen.getByText(HINT);
    expect(help).toHaveClass('auth-help-text');
    expect(help.closest('.auth-form-group')).toContainElement(codeField());
    expect(container.querySelectorAll('.auth-help-text')).toHaveLength(1);
    // No message was given, so no status.
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('describes the code field by the message and the hint together', () => {
    renderContent({initialMessage: ACK, hint: HINT});

    expect(codeField()).toHaveAccessibleDescription(`${ACK} ${HINT}`);
  });

  it('describes the code field by the hint alone when there is no message', () => {
    renderContent({hint: HINT});

    expect(codeField()).toHaveAccessibleDescription(HINT);
  });

  it('replaces the initial message with the resend response and keeps the hint', async () => {
    renderContent({initialMessage: ACK, hint: HINT});
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestLoginCode.mockResolvedValue({message: 'Another code is on its way.'});

    fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

    expect(await screen.findByText('Another code is on its way.')).toBeInTheDocument();
    expect(authValue.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
    expect(screen.queryByText(ACK)).toBeNull();
    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(screen.getByText(HINT)).toBeInTheDocument();
    expect(codeField()).toHaveAccessibleDescription(`Another code is on its way. ${HINT}`);
  });

  it('drops the initial message once a code is submitted, and keeps the hint', async () => {
    renderContent({initialMessage: ACK, hint: HINT});
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyLoginCode.mockRejectedValue(new Error('Invalid or expired code.'));

    fireEvent.change(codeField(), {target: {value: '000000'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

    await waitFor(() => {
      expect(authValue.verifyLoginCode).toHaveBeenCalledWith('ada@example.com', '000000');
    });
    expect(screen.queryByText(ACK)).toBeNull();
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });

  it('still goes Back through the host when it supplies a message and hint', () => {
    const onBack = vi.fn();
    render(
      <MemoryRouter>
        <VerifyEmailPageContent
          flow="login"
          email="ada@example.com"
          returnTo={null}
          onBack={onBack}
          initialMessage={ACK}
          hint={HINT}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(mockNavigate).not.toHaveBeenCalled();
  });
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
