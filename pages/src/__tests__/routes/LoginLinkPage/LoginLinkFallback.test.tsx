import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  captureAuthCallbackParams,
  readAuthCallbackParams,
} from '@/features/auth/api/callbackParams';
import {
  LoginLinkFallback,
  type LoginLinkFallbackKind,
} from '@/routes/LoginLinkPage/LoginLinkFallback';

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

const INSTEAD = "Enter your email and we'll send you a 6-digit code to sign in instead.";
const GENERIC_ACK = 'If an eligible account exists, a verification code has been sent.';

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

const renderFallback = (
  props: {kind?: LoginLinkFallbackKind; returnTo?: string | null; onRetry?: () => void} = {},
) =>
  render(
    <MemoryRouter>
      <LoginLinkFallback kind={props.kind ?? 'invalid'} returnTo={props.returnTo ?? null} onRetry={props.onRetry} />
    </MemoryRouter>,
  );

// What main.tsx does before React mounts: the token moves into the
// sessionStorage handoff and the URL is scrubbed.
const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  captureAuthCallbackParams();
};
const handoffToken = () => readAuthCallbackParams('login-link', new URLSearchParams()).get('token');

const emailField = () => screen.getByLabelText('Email address');
const submit = () => fireEvent.click(screen.getByRole('button', {name: /Send sign-in code|Sending code/}));
const typeEmail = (value: string) => fireEvent.change(emailField(), {target: {value}});
const codeField = () => screen.getByRole('textbox', {name: '6-digit verification code'});
const codeHeading = () => screen.findByRole('heading', {name: 'Verify Login', level: 1});

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

    it('is informational, in the same card layout as the login page', () => {
      const {container} = renderFallback();

      expect(container.querySelector('.auth-page > .auth-page-card')).not.toBeNull();
      expect(container.querySelector('.auth-page-header img.auth-page-logo')).not.toBeNull();
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

  describe('the existing-accounts code flow', () => {
    // The unified email-auth flow creates a pending account for an address it
    // does not know, so a typo here would sign the visitor in as a stranger. A
    // login link only ever exists for an existing member.
    it('never touches the unified email-auth flow, from the request to the sign-in', async () => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      renderFallback();
      typeEmail('nobody@example.com');
      submit();
      await codeHeading();

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(2);
      });
      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });

      expect(auth.requestEmailAuthCode).not.toHaveBeenCalled();
      expect(auth.verifyEmailAuthCode).not.toHaveBeenCalled();
    });

    it('never touches the unified flow when the request fails or the code is wrong either', async () => {
      auth.requestLoginCode.mockRejectedValueOnce(new Error('offline'));
      auth.verifyLoginCode.mockRejectedValue(new Error('Invalid or expired code.'));
      renderFallback();
      typeEmail('ada@example.com');
      submit();
      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledTimes(1);
      });
      submit();
      await codeHeading();
      fireEvent.change(codeField(), {target: {value: '000000'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });

      expect(auth.requestEmailAuthCode).not.toHaveBeenCalled();
      expect(auth.verifyEmailAuthCode).not.toHaveBeenCalled();
    });
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
      expect(screen.getByText('Sending to')).toBeInTheDocument();
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

  describe('the code step', () => {
    const openCodeStep = async (returnTo: string | null = null) => {
      renderFallback({returnTo});
      typeEmail('ada@example.com');
      submit();
      await codeHeading();
    };

    it('puts focus on the code field when it opens, not on <body>', async () => {
      await openCodeStep();

      expect(codeField()).toHaveFocus();
    });

    it('verifies the code through the login flow and continues to the link destination', async () => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      await openCodeStep('/schedule');

      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledWith('ada@example.com', '123456');
      });
      expect(mockNavigate).toHaveBeenCalledWith('/schedule', {replace: true});
    });

    it('continues to /account when the link had no destination', async () => {
      auth.verifyLoginCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});
      await openCodeStep(null);

      fireEvent.change(codeField(), {target: {value: '123456'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
      });
    });

    it('keeps the visitor on the code step when the code is wrong', async () => {
      auth.verifyLoginCode.mockRejectedValue(new Error('Invalid or expired code.'));
      await openCodeStep('/schedule');

      fireEvent.change(codeField(), {target: {value: '000000'}});
      fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

      await waitFor(() => {
        expect(auth.verifyLoginCode).toHaveBeenCalledTimes(1);
      });
      expect(mockNavigate).not.toHaveBeenCalled();
      expect(codeField()).toBeInTheDocument();
    });

    it('resends the code through the same login request', async () => {
      await openCodeStep();
      auth.requestLoginCode.mockClear();
      auth.requestLoginCode.mockResolvedValue({message: 'A new code is on its way.'});

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledWith('ada@example.com');
      });
      expect(await screen.findByText('A new code is on its way.')).toBeInTheDocument();
      // Still on the code step.
      expect(codeField()).toBeInTheDocument();
    });

    it('goes back to the email step, inline, with the address kept and errors cleared', async () => {
      await openCodeStep();
      auth.clearError.mockClear();

      fireEvent.click(screen.getByRole('button', {name: 'Back'}));

      expect(await screen.findByLabelText('Email address')).toHaveValue('ada@example.com');
      expect(emailField()).toHaveFocus();
      expect(auth.clearError).toHaveBeenCalled();
      // The default Back leaves for /login, which would strand a signed-in browser.
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('can send a code to a corrected address after going back', async () => {
      await openCodeStep();
      fireEvent.click(screen.getByRole('button', {name: 'Back'}));
      typeEmail('grace@example.com');
      auth.requestLoginCode.mockClear();
      submit();

      await waitFor(() => {
        expect(auth.requestLoginCode).toHaveBeenCalledWith('grace@example.com');
      });
      expect(await screen.findByText('grace@example.com')).toBeInTheDocument();
      // Focus follows every arrival at the code step, not just the first.
      expect(codeField()).toHaveFocus();
    });
  });
});
