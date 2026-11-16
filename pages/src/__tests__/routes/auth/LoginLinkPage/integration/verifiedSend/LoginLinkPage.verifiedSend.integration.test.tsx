// The fallback's code request goes through the REAL verified-send machinery
// (challenge, proof of work, send) against a fake axios adapter; only the proof
// solver, which needs a browser worker, is replaced. Everything else on the way
// (flows, client, storage, AuthProvider, page) is real.
//
// It reproduces a race that no other test can reach because the shared test
// setup stubs the machinery out: a browser holding a DEAD stored session has it
// cleared by the provider's own check (session 401, then refresh 401) while the
// visitor's code request is still on its way. The stored session's generation
// changes mid-flight; a code request does not depend on it, so the request must
// not be cancelled and the visitor must not see an error.
import {fireEvent, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {getStoredSession} from '@/features/auth/api/session/storage';

import {CODE, finishProof, proofReached, registerVerifiedSendHooks, releaseSessionCheck, renderApp, requestsTo, sendCode, sessionCheckStarted} from '@/__tests__/routes/auth/LoginLinkPage/integration/verifiedSend/verifiedSendIntegrationSetup';

vi.unmock('@/features/auth/verification');

vi.mock('@/features/auth/verification/solve', () => ({
  newRequestId: () => '22222222-2222-4222-8222-222222222222',
  solveAltchaChallenge: vi.fn(),
}));

describe('LoginLinkPage code fallback with the real verified send', () => {
  registerVerifiedSendHooks();

  it('is not cancelled when the dead stored session is cleared while the request is in flight', async () => {
    const generationBefore = getStoredSession()?.generation;
    expect(generationBefore).toBeTruthy();
    renderApp();
    await screen.findByLabelText('Email address');
    // The provider's check of the stale session is under way but unanswered.
    await waitFor(() => expect(sessionCheckStarted).toBe(true));

    sendCode();
    await waitFor(() => expect(proofReached).toBe(true));
    expect(requestsTo('/authn/login/request-code/')).toHaveLength(0);

    // The check now learns the session is dead and clears it: the stored
    // generation the send started under is gone before the proof is finished.
    releaseSessionCheck();
    await waitFor(() => expect(getStoredSession()).toBeNull());
    finishProof();

    // The visitor moves on to the code step: no error, nothing to redo.
    expect(await screen.findByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(/unexpected error/i)).toBeNull();
    expect(screen.getByRole('textbox', {name: '6-digit verification code'})).toHaveFocus();

    // Exactly one code was requested, for the lowercased address, and the
    // request carried the solved proof.
    const sent = requestsTo('/authn/login/request-code/');
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toMatchObject({
      email: 'owner@example.com',
      verification_challenge_id: '11111111-1111-4111-8111-111111111111',
      verification_payload: 'signed-payload',
      send_request_id: '22222222-2222-4222-8222-222222222222',
    });
    expect(requestsTo('/authn/email-auth/request-code/')).toHaveLength(0);

    // ...and the code then signs the visitor in as the link's owner.
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: CODE}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

    expect(await screen.findByText('Schedule page')).toBeInTheDocument();
    expect(getStoredSession()).toMatchObject({user: {member_uuid: 'member-owner'}});
    expect(requestsTo('/authn/login/verify-code/')[0]).toMatchObject({authorization: null});
  });

  it('is not cancelled when the session was already cleared before the request started', async () => {
    renderApp();
    await screen.findByLabelText('Email address');
    await waitFor(() => expect(sessionCheckStarted).toBe(true));
    releaseSessionCheck();
    await waitFor(() => expect(getStoredSession()).toBeNull());

    sendCode();
    await waitFor(() => expect(proofReached).toBe(true));
    finishProof();

    expect(await screen.findByRole('heading', {name: 'Verify Login', level: 1})).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(requestsTo('/authn/login/request-code/')).toHaveLength(1);
  });
});
