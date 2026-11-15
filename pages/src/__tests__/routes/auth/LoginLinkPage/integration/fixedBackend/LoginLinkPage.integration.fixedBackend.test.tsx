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
import {screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {seedHandoff, seedStaleSession, STALE_ACCESS} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixtures/loginLinkIntegrationFixtures';
import {openLink, renderApp, typeCodeAndContinue, typeEmailAndSend} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixedBackend/fixedBackendIntegrationPage';
import {GOOD_CODE, TOKENS, authEvents, loginLinkRequests, refreshRequests, registerFixedBackendHooks, requestsTo, setStaleSessionDead} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixedBackend/fixedBackendIntegrationSetup';

// The code request runs a proof-of-work challenge against three extra endpoints;
// that machinery has its own tests. Everything after it (verify, storage, the
// provider, the event) is real.
vi.mock('@/features/auth/api/signin/flows', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api/signin/flows')>()),
  requestLoginCode: (...args: unknown[]) => mockRequestLoginCode(...args),
}));

const mockRequestLoginCode = vi.fn();

describe('LoginLinkPage falling back to an emailed code against the fixed backend', () => {
  registerFixedBackendHooks(mockRequestLoginCode);

  it.each([
    // A stored session is what makes "already used" continue to /account (the
    // deliberate one-time-link-clicked-twice case), so that link is exercised
    // without one. Every other failure must ignore the stored session.
    ['an expired link, with a stored session', TOKENS.expired, 'This sign-in link has expired.', true],
    ['an expired link, without one', TOKENS.expired, 'This sign-in link has expired.', false],
    ['a used link, without a stored session', TOKENS.used, 'This sign-in link has already been used.', false],
  ])(
    'signs in with the code and lands on the link destination (%s)',
    async (_label, token, sentence, hasStoredSession) => {
      if (hasStoredSession) seedStaleSession();

      const {container} = await openLink(token);

      // Not an error, and not the stale account's /account either.
      expect(screen.getByRole('status').textContent).toBe(
        `${sentence} Enter your email and we'll send you a 6-digit code to sign in instead.`,
      );
      expect(screen.queryByRole('alert')).toBeNull();
      expect(container.querySelector('.magic-login-error')).toBeNull();
      expect(screen.queryByText('Account page')).toBeNull();
      await waitFor(() => expect(screen.getByLabelText('Email address')).toHaveFocus());
      // The anonymous exchange neither used nor destroyed any stored session.
      expect(loginLinkRequests()).toHaveLength(1);
      expect(loginLinkRequests()[0]).toMatchObject({authorization: null, body: {token}});
      expect(refreshRequests()).toHaveLength(0);
      if (hasStoredSession) {
        expect(getStoredSession()).toMatchObject({access: STALE_ACCESS, user: {member_uuid: 'member-old'}});
      } else {
        expect(getStoredSession()).toBeNull();
      }

      await typeEmailAndSend();

      // Inline: no hop to a route that redirects a signed-in browser away.
      expect(mockRequestLoginCode.mock.calls[0]).toEqual(['new@example.com']);
      expect(mockRequestLoginCode).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
      expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toHaveFocus();
      expect(screen.getByText('new@example.com')).toBeInTheDocument();
      expect(screen.queryByText('Login route')).toBeNull();
      expect(screen.queryByText('Verify-email route')).toBeNull();

      const eventsBefore = authEvents;
      typeCodeAndContinue();

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(screen.queryByText('Account page')).toBeNull();

      // The code exchange is anonymous too, and carries exactly what was typed.
      const verifies = requestsTo('/authn/login/verify-code/');
      expect(verifies).toHaveLength(1);
      expect(verifies[0]).toMatchObject({
        authorization: null,
        body: {email: 'new@example.com', code: GOOD_CODE},
      });
      expect(refreshRequests()).toHaveLength(0);

      // Account B replaced account A (if any) in the single session slot.
      expect(getStoredSession()).toMatchObject({
        access: 'new-access',
        refresh: 'new-refresh',
        user: {member_uuid: 'member-new', email: 'new@example.com'},
      });
      expect(localStorage.getItem('i2g_auth_session')).not.toContain(STALE_ACCESS);
      // Every root learns about it.
      expect(authEvents).toBeGreaterThan(eventsBefore);
      // The unified flow (which would create an account for an unknown address)
      // was never used.
      expect(requestsTo('/authn/email-auth/verify-code/')).toHaveLength(0);
    },
  );

  it('sends a used link with a live stored session on to /account, without the fallback', async () => {
    seedStaleSession();
    seedHandoff(TOKENS.used);

    renderApp();

    expect(await screen.findByText('Account page')).toBeInTheDocument();
    expect(screen.queryByLabelText('Email address')).toBeNull();
    expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
  });

  it('offers the code sign-in for a used link whose stored session is dead, and lands on the link destination', async () => {
    // The provider's own check would clear this session as soon as /account
    // opened, leaving the visitor anonymous there and without the link's
    // destination. The page asks first, through the same shared check.
    setStaleSessionDead(true);
    seedStaleSession();
    seedHandoff(TOKENS.used);

    const {container} = renderApp();

    expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('This sign-in link has already been used.');
    expect(container.querySelector('.magic-login-error')).toBeNull();
    expect(screen.queryByText('Account page')).toBeNull();
    // The dead session is gone, and was checked once for both the page and the provider.
    expect(getStoredSession()).toBeNull();
    expect(requestsTo('/authn/session/')).toHaveLength(1);

    await typeEmailAndSend();
    typeCodeAndContinue();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(screen.queryByText('Account page')).toBeNull();
    expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
  });

  it('offers the same fallback, and signs in, with no stored session', async () => {
    await openLink(TOKENS.expired);

    await typeEmailAndSend('new@example.com');
    typeCodeAndContinue();

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
  });
});
