// Two regressions for emailed login links, both driven through the REAL auth
// client, storage, and page against a fake axios adapter.
//
// 1. A link that showed as unusable in a browser that already held a session.
//    The fake behaves like the backend did before its own fix: LoginLinkView ran
//    JWT authentication ahead of the view, so any expired bearer was answered
//    with 401 and the emailed token was never consumed.
//
// 2. A link that cannot be used must not be an error. The fake behaves like the
//    fixed backend and the page falls back to signing in with an emailed code
//    (the existing-accounts `login` flow), inline on /login-link, with the real
//    AuthProvider, so a stored session from another account is replaced rather
//    than stranding the visitor.
import {type AxiosAdapter} from 'axios';
import {fireEvent, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {STALE_ACCESS, reply, seedStaleSession, useAdapter} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixtures/loginLinkIntegrationFixtures';
import {openLink, typeCodeAndContinue, typeEmailAndSend} from '@/__tests__/routes/auth/LoginLinkPage/integration/fallback/fallbackIntegrationPage';
import {TOKENS, fixedBackend, registerFallbackHooks, requestsTo, setCodeReply, setInvalidLinkRedirect, setLinkRedirect, verifyResponse} from '@/__tests__/routes/auth/LoginLinkPage/integration/fallback/fallbackIntegrationSetup';

// The code request runs a proof-of-work challenge against three extra endpoints;
// that machinery has its own tests. Everything after it (verify, storage, the
// provider, the event) is real.
vi.mock('@/features/auth/api/signin/flows', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/signin/flows')>()),
  requestLoginCode: (...args: unknown[]) => mockRequestLoginCode(...args),
}));

const mockRequestLoginCode = vi.fn();

describe('LoginLinkPage falling back to an emailed code — addresses, codes and failures', () => {
  registerFallbackHooks(mockRequestLoginCode);

  it('takes a mistyped address to the same code step, where nothing it could receive signs anyone in', async () => {
    // The login flow answers every address alike, so the page advances; a code
    // for an address without an account is simply rejected. Crucially, no
    // pending account is created and the stored session is left alone: the
    // unified email-auth endpoints are never called.
    seedStaleSession();
    await openLink(TOKENS.expired);
    setCodeReply({status: 400, data: {detail: 'Verification code is invalid or has expired.'}});

    await typeEmailAndSend('typo@example.com');
    expect(screen.getByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
    typeCodeAndContinue('654321');

    expect(await screen.findByRole('alert')).toHaveTextContent('Verification code is invalid or has expired.');
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS, user: {member_uuid: 'member-old'}});
    expect(requestsTo('/authn/email-auth/request-code/')).toHaveLength(0);
    expect(requestsTo('/authn/email-auth/verify-code/')).toHaveLength(0);
  });

  it.each([
    ['an absolute URL', 'https://evil.example/phish'],
    ['a protocol-relative URL', '//evil.example'],
    ['a javascript: URL', 'javascript:alert(1)'],
    ['a backslash path', '/\\evil.example'],
    ['a non-string', {path: '/schedule'}],
    ['nothing (an older backend)', undefined],
  ])('ignores an unusable link destination (%s) and lands on /account', async (_label, redirect) => {
    setLinkRedirect(redirect);
    await openLink(TOKENS.expired);

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Account page')).toBeInTheDocument();
    expect(screen.queryByText('Schedule page')).toBeNull();
  });

  it('never applies a destination from an invalid link', async () => {
    setInvalidLinkRedirect('/schedule');
    await openLink(TOKENS.unknown);
    expect(screen.getByRole('status')).toHaveTextContent("This sign-in link can't be used.");

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Account page')).toBeInTheDocument();
  });

  it('keeps the link destination through a profile-completion detour', async () => {
    await openLink(TOKENS.expired);
    // Answers the code exchange with an account that still has to finish its profile.
    const incomplete = {...verifyResponse, next_step: 'complete_profile', requires_profile_completion: true};
    const adapter: AxiosAdapter = (config) =>
      (config.url ?? '').endsWith('/authn/login/verify-code/')
        ? reply(config, {status: 200, data: incomplete})
        : fixedBackend(config);
    useAdapter(adapter);

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Complete-profile page')).toBeInTheDocument();
  });

  it('shows a wrong code as an error, keeps the stored session, and accepts the right code afterwards', async () => {
    seedStaleSession();
    await openLink(TOKENS.expired);
    await typeEmailAndSend();

    typeCodeAndContinue('000000');

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid or expired code.');
    expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toBeInTheDocument();
    expect(screen.queryByText('Schedule page')).toBeNull();
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});

    typeCodeAndContinue();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(getStoredSession()).toMatchObject({access: 'new-access'});
  });

  it('resends the code from the code step', async () => {
    await openLink(TOKENS.expired);
    await typeEmailAndSend();
    mockRequestLoginCode.mockClear();
    mockRequestLoginCode.mockResolvedValue({message: 'A new code is on its way.'});

    fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

    expect(await screen.findByText('A new code is on its way.')).toBeInTheDocument();
    expect(mockRequestLoginCode.mock.calls[0]).toEqual(['new@example.com']);
    expect(mockRequestLoginCode).toHaveBeenCalledTimes(1);

    // The resent code still signs in.
    typeCodeAndContinue();
    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
  });

  it('goes back from the code step to the email step without leaving the page', async () => {
    seedStaleSession();
    await openLink(TOKENS.expired);
    await typeEmailAndSend();

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));

    expect(await screen.findByLabelText('Email address')).toHaveValue('New@Example.com');
    expect(screen.queryByText('Login route')).toBeNull();
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
  });

  describe('email validation', () => {
    it.each([
      ['an empty field', '', 'Please enter your email address.'],
      ['a name', 'new', 'Please enter a valid email address.'],
      ['a phone number', '2015550123', 'Please enter a valid email address.'],
    ])('rejects %s and sends nothing', async (_label, value, message) => {
      await openLink(TOKENS.expired);

      fireEvent.change(screen.getByLabelText('Email address'), {target: {value}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));

      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(mockRequestLoginCode).not.toHaveBeenCalled();
      expect(screen.queryByRole('textbox', {name: '6-digit verification code'})).toBeNull();
    });

    it('shows a failure to send the code and lets the visitor try again', async () => {
      await openLink(TOKENS.expired);
      mockRequestLoginCode.mockRejectedValueOnce(
        Object.assign(new Error('throttled'), {response: {status: 429, data: {detail: 'Too many requests. Try again later.'}}}),
      );

      fireEvent.change(screen.getByLabelText('Email address'), {target: {value: 'new@example.com'}});
      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));

      expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests. Try again later.');
      expect(screen.getByLabelText('Email address')).toHaveValue('new@example.com');

      fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
      expect(await screen.findByRole('textbox', {name: '6-digit verification code'})).toBeInTheDocument();
    });
  });
});
