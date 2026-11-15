import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  codeField,
  codeHeading,
  emailField,
  GENERIC_ACK,
  INSTEAD,
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
    it('is a labelled, autofocused email field with a hint and the privacy notice', () => {
      renderFallback();

      const field = emailField();
      expect(field).toHaveAttribute('type', 'email');
      expect(field).toHaveAttribute('autocomplete', 'email');
      expect(field).toBeRequired();
      expect(field).toHaveFocus();
      // Why the visitor is here, then how the field works.
      expect(field).toHaveAccessibleDescription(
        `This sign-in link can't be used. ${INSTEAD} We'll email you a 6-digit sign-in code.`,
      );
      expect(screen.getByRole('link', {name: 'Privacy/Legal Notice'})).toHaveAttribute('href', '/privacy');
    });

    it('clears any earlier auth error when it opens', () => {
      renderFallback();

      expect(auth.clearError).toHaveBeenCalled();
    });

    it.each([
      ['nothing', '', 'Please enter your email address.'],
      ['only spaces', '   ', 'Please enter your email address.'],
      ['a name', 'ada', 'Please enter a valid email address.'],
      ['an address without a domain', 'ada@example', 'Please enter a valid email address.'],
      ['two addresses', 'a@example.com b@example.com', 'Please enter a valid email address.'],
      // The sign-in is email-only, so a phone number is as invalid as text.
      ['a phone number', '(201) 555-0123', 'Please enter a valid email address.'],
    ])('rejects %s without sending anything', (_label, value, message) => {
      renderFallback();

      typeEmail(value);
      submit();

      expect(screen.getByRole('alert')).toHaveTextContent(message);
      expect(emailField()).toHaveAttribute('aria-invalid', 'true');
      expect(auth.requestLoginCode).not.toHaveBeenCalled();
      expect(auth.requestEmailAuthCode).not.toHaveBeenCalled();
      // Still on the email step.
      expect(screen.queryByRole('textbox', {name: '6-digit verification code'})).toBeNull();
    });

    it('drops the validation error as soon as the visitor edits the field', () => {
      renderFallback();
      typeEmail('ada');
      submit();
      expect(screen.getByRole('alert')).toBeInTheDocument();

      typeEmail('ada@');

      expect(screen.queryByRole('alert')).toBeNull();
      expect(emailField()).toHaveAttribute('aria-invalid', 'false');
    });

    it('validates on submit even for an empty form (the button stays enabled)', () => {
      renderFallback();

      expect(screen.getByRole('button', {name: 'Send sign-in code'})).toBeEnabled();
    });

    it('shows an error from the auth context in an alert', () => {
      mockUseAuth.mockReturnValue(buildAuth({error: 'Too many requests. Try again later.'}));
      renderFallback();

      expect(screen.getByRole('alert')).toHaveTextContent('Too many requests. Try again later.');
    });

    it('disables the submit button and says so while the code is being sent', () => {
      mockUseAuth.mockReturnValue(buildAuth({isLoading: true}));
      renderFallback();

      const button = screen.getByRole('button', {name: /Sending code/});
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('type', 'submit');
    });

    it('does not send again when the form is submitted while a code is being sent', () => {
      const busy = buildAuth({isLoading: true});
      mockUseAuth.mockReturnValue(busy);
      renderFallback();

      typeEmail('ada@example.com');
      fireEvent.submit(emailField().closest('form')!);

      expect(busy.requestLoginCode).not.toHaveBeenCalled();
    });

    it('requests a login code for the trimmed, lowercased address, then shows the code step', async () => {
      renderFallback();

      typeEmail('  Ada@Example.COM ');
      submit();

      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
      });
      expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      expect(await codeHeading()).toBeInTheDocument();
      expect(screen.getByText('ada@example.com')).toBeInTheDocument();
      expect(codeField()).toBeInTheDocument();
      expect(screen.queryByLabelText('Email address')).toBeNull();
      // Nothing left the page.
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('advances to the code step for whatever address the server accepts, revealing nothing about it', async () => {
      // The login flow answers an unknown or ineligible address exactly like a
      // known one, so the page cannot and must not tell them apart.
      auth.requestLoginCode.mockResolvedValue({message: GENERIC_ACK});
      renderFallback();

      typeEmail('nobody-here@example.com');
      submit();

      expect(await codeHeading()).toBeInTheDocument();
      expect(screen.queryByRole('alert')).toBeNull();
      expect(screen.queryByText(/no account|not found|doesn't exist|does not exist/i)).toBeNull();
    });
  });
});
