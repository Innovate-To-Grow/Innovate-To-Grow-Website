import {beforeEach, describe, expect, it, vi} from 'vitest';
import {webcrypto} from 'node:crypto';

vi.unmock('@/features/auth/verification');
vi.mock('@/features/auth/verification/api', () => ({createSendChallenge: vi.fn(), fetchSendRequestStatus: vi.fn()}));
vi.mock('@/features/auth/verification/solve', () => ({newRequestId: () => '22222222-2222-4222-8222-222222222222', solveAltchaChallenge: vi.fn(async () => 'signed-payload')}));

import {createSendChallenge, fetchSendRequestStatus} from '@/features/auth/verification/api';
import {solveAltchaChallenge} from '@/features/auth/verification/solve';
import {withVerifiedSend} from '@/features/auth/verification/withVerifiedSend';
import {setVerifiedSendStatus} from '@/features/auth/verification/status';
import type {SendVerificationOperation} from '@/features/auth/verification/types';

let sequence = 0;
const storeSession = (generation: string) => {
  localStorage.setItem('i2g_auth_session', JSON.stringify({version: 1, generation, access: 'access', refresh: 'refresh', user: {member_uuid: 'member', email: 'member@example.com'}, requires_profile_completion: false}));
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};
const clearSession = () => {
  localStorage.removeItem('i2g_auth_session');
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};
const accepted = {request_id: 'request', status: 'provider_accepted' as const, code: null, http_status: 202, result: {message: 'sent'}, challenge_id: null};
const options = (execute = vi.fn().mockResolvedValue({message: 'sent'})) => ({
  operation: 'email_auth.request_code' as SendVerificationOperation,
  destinationKind: 'email' as const,
  destination: `person-${sequence++}@example.com`,
  execute,
});

describe('withVerifiedSend', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', webcrypto);
    const storage = () => {
      const values = new Map<string, string>();
      return {getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key), get length() {return values.size;}};
    };
    vi.stubGlobal('localStorage', storage());
    vi.stubGlobal('sessionStorage', storage());
    vi.mocked(createSendChallenge).mockReset().mockResolvedValue({
      challenge_id: '11111111-1111-4111-8111-111111111111',
      expires_at: new Date().toISOString(), algorithm: 'PBKDF2/SHA-256', cost: 100,
      challenge: {parameters: {algorithm: 'PBKDF2/SHA-256', cost: 100}},
    });
    vi.mocked(fetchSendRequestStatus).mockReset().mockResolvedValue(accepted);
    vi.mocked(solveAltchaChallenge).mockReset().mockResolvedValue('signed-payload');
    setVerifiedSendStatus({phase: 'idle', message: ''});
  });

  // The server binds these operations to the signed-in member, and every other
  // one to the browser's Django session cookie (AUTHENTICATED_OPERATIONS in
  // apps/authn/services/send_verification/rules/constants.py). A change of the stored
  // JWT session matters to the first kind only.
  const OPERATIONS: Array<[SendVerificationOperation, 'member' | 'anonymous']> = [
    ['email_auth.request_code', 'anonymous'],
    ['phone_auth.request_code', 'anonymous'],
    ['login.request_code', 'anonymous'],
    ['register', 'anonymous'],
    ['register.resend_code', 'anonymous'],
    ['password_reset.request_code', 'anonymous'],
    ['admin.login.request_code', 'anonymous'],
    ['admin.login.remembered_code', 'anonymous'],
    ['admin.login.resend', 'anonymous'],
    ['change_password.request_code', 'member'],
    ['delete_account.request_code', 'member'],
    ['contact_email.create', 'member'],
    ['contact_email.request_verification', 'member'],
    ['contact_phone.request_verification', 'member'],
    ['event.send_phone_code', 'member'],
    ['event.send_secondary_email_code', 'member'],
  ];

  describe.each(OPERATIONS)('%s (%s operation)', (operation, kind) => {
    const sendWhile = (during: () => void) => {
      vi.mocked(solveAltchaChallenge).mockImplementation(async () => {
        during();
        return 'signed-payload';
      });
      const input = {...options(), operation};
      return {input, result: withVerifiedSend(input)};
    };

    const expectOutcome = async (input: ReturnType<typeof options>, result: Promise<unknown>) => {
      if (kind === 'member') {
        await expect(result).rejects.toMatchObject({name: 'AbortError'});
        expect(input.execute).not.toHaveBeenCalled();
      } else {
        await expect(result).resolves.toEqual({message: 'sent'});
        expect(input.execute).toHaveBeenCalledTimes(1);
      }
    };

    it(`${kind === 'member' ? 'is cancelled' : 'still sends'} when another account replaces the session mid-flight`, async () => {
      storeSession('account-a');
      const {input, result} = sendWhile(() => storeSession('account-b'));
      await expectOutcome(input, result);
    });

    it(`${kind === 'member' ? 'is cancelled' : 'still sends'} when the session is cleared mid-flight`, async () => {
      // What the auth bootstrap does to a dead stored session while a code is
      // being requested.
      storeSession('account-a');
      const {input, result} = sendWhile(clearSession);
      await expectOutcome(input, result);
    });
  });

  it('keeps one in-flight anonymous send through a session change, so a repeat action joins it', async () => {
    const releases: Array<() => void> = [];
    vi.mocked(solveAltchaChallenge).mockImplementation(
      () => new Promise((resolve) => releases.push(() => resolve('signed-payload'))),
    );
    storeSession('account-a');
    const input = {...options(), operation: 'login.request_code' as const};

    const first = withVerifiedSend(input);
    await vi.waitFor(() => expect(releases).toHaveLength(1));
    storeSession('account-b');
    const second = withVerifiedSend(input);
    releases[0]();

    await expect(Promise.all([first, second])).resolves.toEqual([{message: 'sent'}, {message: 'sent'}]);
    expect(input.execute).toHaveBeenCalledTimes(1);
    expect(createSendChallenge).toHaveBeenCalledTimes(1);
  });

  it('never lets a member-bound send started under another account stand in for the new one', async () => {
    const releases: Array<() => void> = [];
    vi.mocked(solveAltchaChallenge).mockImplementation(
      () => new Promise((resolve) => releases.push(() => resolve('signed-payload'))),
    );
    storeSession('account-a');
    const input = {...options(), operation: 'change_password.request_code' as const};

    const first = withVerifiedSend(input).then(
      () => 'sent',
      (error: Error) => error.name,
    );
    await vi.waitFor(() => expect(releases).toHaveLength(1));
    storeSession('account-b');
    const second = withVerifiedSend(input);
    await vi.waitFor(() => expect(releases).toHaveLength(2));
    releases.forEach((release) => release());

    await expect(first).resolves.toBe('AbortError');
    await expect(second).resolves.toEqual({message: 'sent'});
    expect(input.execute).toHaveBeenCalledTimes(1);
  });
});
