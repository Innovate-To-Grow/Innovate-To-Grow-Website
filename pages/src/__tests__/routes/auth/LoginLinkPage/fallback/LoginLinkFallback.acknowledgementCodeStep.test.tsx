import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  codeField,
  codeHeading,
  GENERIC_ACK,
  renderFallback,
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

  describe('the acknowledgement on the code step', () => {
    // The login flow answers every address with one generic sentence, so what
    // the page shows after a request must be that sentence and nothing that
    // depends on whether the address belongs to a member.
    const HINT = "Didn't get a code? Check the address above or go back to correct it.";
    const openFor = async (address: string) => {
      renderFallback();
      typeEmail(address);
      submit();
      await codeHeading();
    };

    it("shows the server's message as an info status, with the hint under the code field", async () => {
      await openFor('ada@example.com');

      const status = screen.getByRole('status');
      expect(status).toHaveClass('auth-alert', 'info');
      expect(status).toHaveTextContent(GENERIC_ACK);
      expect(screen.getByText(HINT)).toHaveClass('auth-help-text');
      // Alongside, not instead of, the address block.
      expect(screen.getByText('Code sent to')).toBeInTheDocument();
      expect(screen.getAllByText('ada@example.com')).toHaveLength(1);
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('shows the message the server sent, not a wording of its own', async () => {
      auth.requestLoginCode.mockResolvedValue({message: 'Whatever the server says today.'});

      await openFor('ada@example.com');

      expect(screen.getByRole('status')).toHaveTextContent('Whatever the server says today.');
      expect(screen.queryByText(GENERIC_ACK)).toBeNull();
    });

    it('reads the same for an address that belongs to nobody as for one that does', async () => {
      await openFor('ada@example.com');
      const known = {status: screen.getByRole('status').textContent, hint: screen.getByText(HINT).textContent};
      cleanup();

      await openFor('nobody-here@example.com');

      expect(screen.getByRole('status').textContent).toBe(known.status);
      expect(screen.getByText(HINT).textContent).toBe(known.hint);
      expect(screen.getByRole('status').textContent).toBe(GENERIC_ACK);
      // Nothing on the step is about the account, only about the address typed.
      expect(screen.queryByText(/no account|not found|doesn't exist|does not exist|not registered/i)).toBeNull();
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('reads the message and the hint as the code field description', async () => {
      await openFor('ada@example.com');

      expect(codeField()).toHaveAccessibleDescription(`${GENERIC_ACK} ${HINT}`);
    });

    it.each<[string, unknown]>([
      ['no body', undefined],
      ['no message', {}],
      ['a blank message', {message: '   '}],
      ['a message that is not text', {message: 42}],
      ['an HTML page instead of a message', {message: '<!DOCTYPE html><html><body>proxy</body></html>'}],
      ['a message too long to be ours', {message: 'x'.repeat(301)}],
    ])('shows only the hint when the server sent %s', async (_label, response) => {
      auth.requestLoginCode.mockResolvedValue(response);

      await openFor('ada@example.com');

      expect(screen.queryByRole('status')).toBeNull();
      expect(screen.getByText(HINT)).toBeInTheDocument();
      expect(codeField()).toHaveAccessibleDescription(HINT);
    });

    it("replaces the message with the new server message when the code is resent, keeping the hint", async () => {
      await openFor('ada@example.com');
      auth.requestLoginCode.mockResolvedValue({message: 'A new code is on its way.'});

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      expect(await screen.findByText('A new code is on its way.')).toBeInTheDocument();
      expect(screen.queryByText(GENERIC_ACK)).toBeNull();
      expect(screen.getAllByRole('status')).toHaveLength(1);
      expect(screen.getByText(HINT)).toBeInTheDocument();
    });

    it('drops the message, not the hint, when a resend fails', async () => {
      await openFor('ada@example.com');
      auth.requestLoginCode.mockRejectedValue(new Error('offline'));

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await waitFor(() => {
        expect(screen.queryByText(GENERIC_ACK)).toBeNull();
      });
      expect(screen.getByText(HINT)).toBeInTheDocument();
    });

    it('goes Back to the email step without the message or hint, and the next request brings its own', async () => {
      await openFor('ada@example.com');

      fireEvent.click(screen.getByRole('button', {name: 'Back'}));

      expect(await screen.findByLabelText('Email address')).toHaveValue('ada@example.com');
      expect(screen.queryByText(GENERIC_ACK)).toBeNull();
      expect(screen.queryByText(HINT)).toBeNull();

      auth.requestLoginCode.mockResolvedValue({message: 'Second request accepted.'});
      typeEmail('grace@example.com');
      submit();
      await codeHeading();

      expect(screen.getByRole('status')).toHaveTextContent('Second request accepted.');
      expect(screen.getByText(HINT)).toBeInTheDocument();
    });

    it('does not show it while the request has not succeeded', async () => {
      auth.requestLoginCode.mockRejectedValue(new Error('offline'));
      renderFallback();

      typeEmail('ada@example.com');
      submit();
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      });

      // Still the email step: its own notice is the only status, and no hint.
      expect(screen.getAllByRole('status')).toHaveLength(1);
      expect(screen.queryByText(GENERIC_ACK)).toBeNull();
      expect(screen.queryByText(HINT)).toBeNull();
    });
  });
});
