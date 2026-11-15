import {fireEvent, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {getStoredSession} from '@/features/auth/api/session/storage';
import {STALE_ACCESS, seedHandoff, seedStaleSession} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixtures/loginLinkIntegrationFixtures';
import {handoffToken, openLink, renderApp, typeCodeAndContinue, typeEmailAndSend} from '@/__tests__/routes/auth/LoginLinkPage/integration/fallback/fallbackIntegrationPage';
import {TOKENS, flakyCalls, loginLinkRequests, memberBResponse, refreshRequests, registerFallbackHooks, setCodeAccount} from '@/__tests__/routes/auth/LoginLinkPage/integration/fallback/fallbackIntegrationSetup';

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

  describe('a retryable failure', () => {
    it('offers the fallback and a retry; the retry signs in through the link itself', async () => {
      seedStaleSession();
      await openLink(TOKENS.flaky);

      expect(screen.getByRole('status')).toHaveTextContent("We couldn't verify your sign-in link right now.");
      expect(screen.queryByRole('alert')).toBeNull();
      expect(handoffToken()).toBe(TOKENS.flaky);

      fireEvent.click(screen.getByRole('button', {name: 'Try the link again'}));

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(loginLinkRequests()).toHaveLength(2);
      expect(loginLinkRequests().every((request) => request.authorization === null)).toBe(true);
      expect(refreshRequests()).toHaveLength(0);
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
      expect(handoffToken()).toBeNull();
    });

    it('drops the retained link once the visitor signs in by code, so a bare /login-link cannot swap the account', async () => {
      // A 503 keeps the emailed token in sessionStorage for Retry or a reload.
      // The visitor then signs in as member B by code. Replaying the retained
      // token later would sign this browser in as the link's owner instead.
      setCodeAccount(memberBResponse);
      seedStaleSession();
      const first = await openLink(TOKENS.flaky);
      expect(handoffToken()).toBe(TOKENS.flaky);

      await typeEmailAndSend('b@example.com');
      expect(handoffToken()).toBeNull();
      typeCodeAndContinue();
      expect(await screen.findByText('Account page')).toBeInTheDocument();
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-b'}});
      first.unmount();

      // Later, in the same tab, a bare /login-link (no token in the URL).
      window.history.replaceState(null, '', '/login-link');
      renderApp();

      expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent("This sign-in link can't be used.");
      expect(screen.queryByRole('alert')).toBeNull();
      // Only the first, failed exchange ever left the browser.
      expect(loginLinkRequests()).toHaveLength(1);
      expect(flakyCalls).toBe(1);
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-b'}});
    });

    it('lets Back then Retry still use the token held in memory after the code step opened', async () => {
      seedStaleSession();
      await openLink(TOKENS.flaky);

      await typeEmailAndSend('b@example.com');
      expect(handoffToken()).toBeNull();
      fireEvent.click(screen.getByRole('button', {name: 'Back'}));
      fireEvent.click(await screen.findByRole('button', {name: 'Try the link again'}));

      expect(await screen.findByText('Schedule page')).toBeInTheDocument();
      expect(loginLinkRequests()).toHaveLength(2);
      expect(loginLinkRequests()[1]).toMatchObject({body: {token: TOKENS.flaky}});
      expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-new'}});
    });

    it('treats a 2xx answer that is not a login as retryable, never as a blocked browser', async () => {
      seedStaleSession();
      const {container} = await openLink(TOKENS.html);

      expect(screen.getByRole('status')).toHaveTextContent("We couldn't verify your sign-in link right now.");
      expect(screen.getByRole('button', {name: 'Try the link again'})).toBeInTheDocument();
      expect(screen.queryByText(/blocked saving/i)).toBeNull();
      expect(container.querySelector('.magic-login-error')).toBeNull();
      expect(screen.queryByRole('alert')).toBeNull();
      // The token was not consumed, so it is kept for a retry or a reload.
      expect(handoffToken()).toBe(TOKENS.html);
      // Nothing malformed reached storage, and the stale session is untouched.
      expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
    });
  });

  describe('a browser that cannot store the session', () => {
    it('keeps the plain error, with no fallback, because a code sign-in could not persist either', async () => {
      seedStaleSession();
      seedHandoff(TOKENS.ok);
      const setItem = Storage.prototype.setItem;
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
        if (this === window.localStorage) {
          throw new DOMException('Storage is unavailable', 'QuotaExceededError');
        }
        return setItem.call(this, key, value);
      });

      const {container} = renderApp();

      expect(
        await screen.findByText('Your browser blocked saving your login session. Please log in manually.'),
      ).toBeInTheDocument();
      expect(container.querySelector('.magic-login-error')).not.toBeNull();
      expect(screen.getByRole('link', {name: 'Go to Login'})).toBeInTheDocument();
      expect(screen.queryByLabelText('Email address')).toBeNull();
      expect(screen.queryByRole('button', {name: 'Try the link again'})).toBeNull();
      // The exchange happened exactly once and its token is gone.
      expect(loginLinkRequests()).toHaveLength(1);
      expect(handoffToken()).toBeNull();
      expect(getStoredSession()).toMatchObject({access: STALE_ACCESS});
    });
  });
});
