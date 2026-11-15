import {useCallback, useState} from 'react';
import {sendPhoneCode, verifyPhoneCode, type EventRegistrationOptions} from '@/features/events/api';
import {maxPhoneDigits, validatePhoneDigits} from '@/lib/format';
import {runLatestRequest, useContactChallenge} from './contactChallenge';

type MemberPhone = NonNullable<EventRegistrationOptions['member_phone']>;

const canVerify = (options: EventRegistrationOptions | null): options is EventRegistrationOptions =>
  Boolean(options?.slug && options.collect_phone && options.verify_phone);

/** The national digits of a stored number (US-only: a leading +1 is stripped). */
const nationalDigits = (stored: string) => (stored.startsWith('+1') ? stored.slice(2) : stored) || stored;

/**
 * The attendee phone and its SMS verification. Each send/verify takes a request number; editing the
 * phone (or leaving the event) bumps it, so a response for an earlier phone never lands.
 */
export function usePhoneVerification(onError: (message: string | null) => void) {
  const [phone, setPhone] = useState('');
  const [region, setRegion] = useState('1-US');
  const [normalizedPhone, setNormalizedPhone] = useState('');
  // Snapshot of the phone as loaded from the member profile. Held in state (not a ref)
  // because `phoneChanged` is derived during render and must react when the snapshot is set.
  const [initialPhone, setInitialPhone] = useState<{digits: string; region: string} | null>(null);
  const challenge = useContactChallenge(setNormalizedPhone);
  const {abandonChallenge, setVerified, setCodeSent} = challenge;

  const reset = useCallback(() => {
    abandonChallenge();
    setPhone('');
    setRegion('1-US');
    setInitialPhone(null);
  }, [abandonChallenge]);

  const prefill = useCallback(
    (memberPhone: MemberPhone) => {
      const digits = nationalDigits(memberPhone.phone_number || '');
      setPhone(digits);
      setRegion('1-US');
      setVerified(Boolean(memberPhone.verified));
      setCodeSent(Boolean(memberPhone.verified));
      setInitialPhone({digits, region: '1-US'});
    },
    [setCodeSent, setVerified],
  );

  const changePhone = (value: string) => {
    const capped = value.slice(0, maxPhoneDigits());
    if (capped !== phone) {
      abandonChallenge();
    }
    setPhone(capped);
  };

  const phoneChanged = initialPhone === null || phone !== initialPhone.digits || region !== initialPhone.region;
  // A number already on the profile is not re-validated; a new or edited one is.
  const phoneError = phone.trim() && phoneChanged ? validatePhoneDigits(phone.trim()) : null;

  const send = async (options: EventRegistrationOptions | null) => {
    if (!canVerify(options) || !phone.trim() || validatePhoneDigits(phone.trim())) return;
    challenge.setVerifying(false);
    challenge.dropChallengeState();
    await runLatestRequest(
      challenge.requestRef,
      challenge.setSending,
      onError,
      () => sendPhoneCode(phone.trim(), region, options.slug),
      (result) => {
        setNormalizedPhone(result.phone);
        challenge.setChallengeId(result.challenge_id);
        setCodeSent(true);
      },
    );
  };

  const verify = async (options: EventRegistrationOptions | null) => {
    const {code, challengeId} = challenge;
    if (!canVerify(options) || !normalizedPhone || !challengeId || code.length !== 6) return;
    await runLatestRequest(
      challenge.requestRef,
      challenge.setVerifying,
      onError,
      () => verifyPhoneCode(normalizedPhone, code.trim(), challengeId, options.slug),
      (result) => {
        setNormalizedPhone(result.phone);
        challenge.setChallengeId(result.challenge_id);
        setVerified(result.verified);
        onError(null);
      },
    );
  };

  return {
    phone,
    region,
    code: challenge.code,
    setCode: challenge.setCode,
    verified: challenge.verified,
    challengeId: challenge.challengeId,
    sending: challenge.sending,
    codeSent: challenge.codeSent,
    verifying: challenge.verifying,
    phoneError,
    invalidate: challenge.invalidate,
    clearChallenge: challenge.clearChallenge,
    reset,
    prefill,
    changePhone,
    send,
    verify,
  };
}

export type PhoneVerification = ReturnType<typeof usePhoneVerification>;
