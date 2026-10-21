import {useCallback, useState} from 'react';
import {sendSecondaryEmailCode, verifySecondaryEmailCode, type EventRegistrationOptions} from '@/features/events/api';
import {getSecondaryEmailError, normalizeRegistrationEmail} from '../steps/helpers';
import {runLatestRequest, useContactChallenge} from './contactChallenge';

const canVerify = (options: EventRegistrationOptions | null): options is EventRegistrationOptions =>
  Boolean(options?.slug && options.allow_secondary_email && options.verify_secondary_email);

/**
 * The attendee's secondary email and its code verification, sequenced like the phone: editing the
 * address (or leaving the event) bumps the request number so a stale response never lands.
 */
export function useSecondaryEmailVerification(onError: (message: string | null) => void) {
  const [email, setEmail] = useState('');
  const [verificationToken, setVerificationToken] = useState('');
  const challenge = useContactChallenge(setVerificationToken);
  const {abandonChallenge, setVerified} = challenge;

  const reset = useCallback(() => {
    abandonChallenge();
    setEmail('');
  }, [abandonChallenge]);

  /** Prefill from the options response; only the current response format can mark it verified. */
  const prefill = useCallback(
    (options: EventRegistrationOptions) => {
      const secondaryEmail = options.member_secondary_email;
      // An older options response can prefill an address, but cannot establish verification.
      setEmail(secondaryEmail === undefined ? options.member_emails?.[1] || '' : secondaryEmail?.email_address || '');
      setVerified(Boolean(secondaryEmail?.verified));
    },
    [setVerified],
  );

  const changeEmail = (value: string) => {
    if (normalizeRegistrationEmail(value) !== normalizeRegistrationEmail(email)) {
      abandonChallenge();
    }
    setEmail(value);
  };

  const send = async (options: EventRegistrationOptions | null, primaryEmail: string) => {
    const address = normalizeRegistrationEmail(email);
    if (!canVerify(options) || !address || getSecondaryEmailError(address, primaryEmail)) return;
    challenge.setVerifying(false);
    challenge.dropChallengeState();
    await runLatestRequest(
      challenge.requestRef,
      challenge.setSending,
      onError,
      () => sendSecondaryEmailCode(address, options.slug),
      (result) => {
        challenge.setChallengeId(result.challenge_id);
        challenge.setCodeSent(true);
      },
    );
  };

  const verify = async (options: EventRegistrationOptions | null) => {
    const {code, challengeId} = challenge;
    if (!canVerify(options) || !challengeId || code.length !== 6) return;
    await runLatestRequest(
      challenge.requestRef,
      challenge.setVerifying,
      onError,
      () => verifySecondaryEmailCode(normalizeRegistrationEmail(email), code, challengeId, options.slug),
      (result) => {
        challenge.setChallengeId(result.challenge_id);
        setVerificationToken(result.verification_token);
        setVerified(result.verified);
        onError(null);
      },
    );
  };

  return {
    email,
    code: challenge.code,
    setCode: challenge.setCode,
    verified: challenge.verified,
    challengeId: challenge.challengeId,
    verificationToken,
    sending: challenge.sending,
    codeSent: challenge.codeSent,
    verifying: challenge.verifying,
    invalidate: challenge.invalidate,
    clearChallenge: challenge.clearChallenge,
    reset,
    prefill,
    changeEmail,
    send,
    verify,
  };
}

export type SecondaryEmailVerification = ReturnType<typeof useSecondaryEmailVerification>;
