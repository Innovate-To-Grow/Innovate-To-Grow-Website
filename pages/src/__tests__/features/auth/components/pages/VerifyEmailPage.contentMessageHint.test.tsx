import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {VerifyEmailPageContent} from '@/features/auth/components/pages/VerifyEmailPage';
import {renderPage} from '@/__tests__/features/auth/components/pages/verifyEmailPageFixtures';

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
