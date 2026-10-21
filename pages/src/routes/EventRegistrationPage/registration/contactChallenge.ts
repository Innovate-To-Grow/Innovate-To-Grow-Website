import {useCallback, useRef, useState, type RefObject} from 'react';
import {getRegistrationErrorMessage} from '../steps/helpers';

/**
 * Run one send or verify request under the next request number. Only the latest request (editing the
 * contact or leaving the event bumps the number) may apply its result, report its error or end its busy flag.
 */
export async function runLatestRequest<T>(
  requestRef: RefObject<number>,
  setBusy: (busy: boolean) => void,
  onError: (message: string | null) => void,
  request: () => Promise<T>,
  apply: (result: T) => void,
) {
  const requestId = ++requestRef.current;
  const isLatest = () => requestId === requestRef.current;
  setBusy(true);
  onError(null);
  try {
    const result = await request();
    if (isLatest()) apply(result);
  } catch (err: unknown) {
    if (isLatest()) onError(getRegistrationErrorMessage(err));
  } finally {
    if (isLatest()) setBusy(false);
  }
}

/**
 * A contact's code challenge: the code typed, whether it was sent and verified, the challenge id, the
 * send/verify busy flags and the request number. ``setIssuedValue`` clears the one value the server
 * hands back with the challenge (the normalized phone, the email verification token) along with it;
 * pass a state setter so the callbacks stay stable.
 */
export function useContactChallenge(setIssuedValue: (value: string) => void) {
  const [code, setCode] = useState('');
  const [verified, setVerified] = useState(false);
  const [challengeId, setChallengeId] = useState('');
  const [sending, setSending] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const requestRef = useRef(0);

  const invalidate = useCallback(() => {
    requestRef.current += 1;
  }, []);

  /** Forget the challenge without touching the request number (a new send takes the next one). */
  const dropChallengeState = useCallback(() => {
    setVerified(false);
    setCodeSent(false);
    setCode('');
    setChallengeId('');
    setIssuedValue('');
  }, [setIssuedValue]);

  /** Drop the challenge (the server asked for a new verification); the contact itself stays. */
  const clearChallenge = useCallback(() => {
    invalidate();
    dropChallengeState();
  }, [dropChallengeState, invalidate]);

  /** Drop the challenge and end any send or verify in progress (the contact was edited or reset). */
  const abandonChallenge = useCallback(() => {
    clearChallenge();
    setSending(false);
    setVerifying(false);
  }, [clearChallenge]);

  return {
    code,
    setCode,
    verified,
    setVerified,
    challengeId,
    setChallengeId,
    sending,
    setSending,
    codeSent,
    setCodeSent,
    verifying,
    setVerifying,
    requestRef,
    invalidate,
    dropChallengeState,
    clearChallenge,
    abandonChallenge,
  };
}
