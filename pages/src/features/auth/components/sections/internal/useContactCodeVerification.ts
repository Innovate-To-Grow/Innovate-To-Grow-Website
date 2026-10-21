import {useState, type FormEvent} from 'react';

const CODE_SENT_MESSAGE = 'Code sent. Enter it below and tap Submit code.';
const CODE_RESENT_MESSAGE = 'New code sent. Enter it below and tap Submit code.';

interface UseContactCodeVerificationOptions<T> {
  requestCode: (contactId: string) => Promise<unknown>;
  verifyCode: (contactId: string, code: string) => Promise<T>;
  /** The verified contact came back from the server; put it in the list. */
  onVerified: (updated: T, contactId: string) => void;
  verifiedMessage: string;
  errorMessage: (err: unknown) => string;
  /** Page-level messages of the contact center that owns this verification. */
  messages: {clear: () => void; setError: (message: string | null) => void; setSuccess: (message: string) => void};
  /** A reason the code may not be submitted yet (shown as the verification error), or null. */
  blockSubmit?: (contactId: string) => string | null;
  /** Runs before the code is checked (e.g. saving a choice made while the code was pending). */
  beforeVerify?: (contactId: string) => Promise<void>;
  /** The confirmation after a resend; null shows none. */
  resendMessage?: (contactId: string) => string | null;
}

/**
 * Verifying one contact (an email address or phone number) at a time with a 6-digit code: request a code,
 * enter it, resend, or cancel. The owning contact center supplies the API calls and its messages.
 */
export function useContactCodeVerification<T>({
  requestCode,
  verifyCode: verifyContactCode,
  onVerified,
  verifiedMessage,
  errorMessage,
  messages,
  blockSubmit,
  beforeVerify,
  resendMessage = () => CODE_RESENT_MESSAGE,
}: UseContactCodeVerificationOptions<T>) {
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);

  /** Open the code field for ``contactId`` (or close it with null), clearing the typed code. */
  const showCodeField = (contactId: string | null) => {
    setVerifyingId(contactId);
    setVerifyCode('');
  };

  /** Show the code field for a contact whose code was just sent (e.g. right after adding it). */
  const begin = (contactId: string) => showCodeField(contactId);

  const cancel = () => {
    showCodeField(null);
    setVerifyError(null);
  };

  /** The contact went away (deleted): close its code field. */
  const forget = (contactId: string) => {
    if (verifyingId === contactId) showCodeField(null);
  };

  /** Send a code to an existing contact and open its code field. */
  const requestVerification = async (contactId: string) => {
    messages.clear();
    setVerifyError(null);
    setVerifyCode('');
    setResendLoading(true);
    try {
      await requestCode(contactId);
      setVerifyingId(contactId);
      messages.setSuccess(CODE_SENT_MESSAGE);
    } catch (err) {
      messages.setError(errorMessage(err));
    } finally {
      setResendLoading(false);
    }
  };

  const resend = async (contactId: string) => {
    setResendLoading(true);
    setVerifyError(null);
    try {
      await requestCode(contactId);
      const confirmation = resendMessage(contactId);
      if (confirmation) messages.setSuccess(confirmation);
    } catch (err) {
      setVerifyError(errorMessage(err));
    } finally {
      setResendLoading(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!verifyingId || verifyCode.length !== 6) return;
    const contactId = verifyingId;
    const blocked = blockSubmit?.(contactId);
    if (blocked) {
      setVerifyError(blocked);
      return;
    }
    setVerifyLoading(true);
    setVerifyError(null);
    messages.clear();
    try {
      await beforeVerify?.(contactId);
      const updated = await verifyContactCode(contactId, verifyCode);
      onVerified(updated, contactId);
      showCodeField(null);
      messages.setSuccess(verifiedMessage);
    } catch (err) {
      setVerifyError(errorMessage(err));
    } finally {
      setVerifyLoading(false);
    }
  };

  return {
    verifyingId,
    setVerifyingId,
    verifyCode,
    setVerifyCode,
    verifyLoading,
    verifyError,
    setVerifyError,
    resendLoading,
    begin,
    cancel,
    forget,
    requestVerification,
    resend,
    submit,
  };
}
