import {useEffect, useState} from 'react';
import {
  deleteContactEmail,
  getContactEmails,
  requestContactEmailVerification,
  updateContactEmail,
  verifyContactEmailCode,
  type ContactEmail,
  type ProfileResponse,
} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';
import {useContactCodeVerification} from './useContactCodeVerification';
import {useAddEmailForm} from './useAddEmailForm';
import {usePrimaryEmailActions} from './usePrimaryEmailActions';
import {usePrimaryEmailVerification} from './usePrimaryEmailVerification';

interface UseEmailCenterOptions {
  profile: ProfileResponse;
  onProfileUpdate: (updated: ProfileResponse) => void;
}

/**
 * The account's email addresses: the primary one (subscribe, verify, remove) and connected ones (add,
 * verify, change type, make primary, remove). Verification flows live in their own hooks.
 */
/** The connected-address code verification, under the names the email center's views use. */
const connectedEmailVerification = (verification: ReturnType<typeof useContactCodeVerification<ContactEmail>>) => ({
  resendLoading: verification.resendLoading,
  verifyCode: verification.verifyCode,
  verifyError: verification.verifyError,
  verifyLoading: verification.verifyLoading,
  verifyingId: verification.verifyingId,
  setVerifyCode: verification.setVerifyCode,
  setVerifyError: verification.setVerifyError,
  setVerifyingId: verification.setVerifyingId,
  handleResend: verification.resend,
  handleContactRequestVerification: verification.requestVerification,
  handleVerifySubmit: verification.submit,
});

export const useEmailCenter = ({profile, onProfileUpdate}: UseEmailCenterOptions) => {
  const [contactEmails, setContactEmails] = useState<ContactEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    const fetchEmails = async () => {
      try {
        setContactEmails(await getContactEmails());
      } catch (err) {
        console.error('[EmailCenter] Failed to load contact emails:', err);
      } finally {
        setLoading(false);
      }
    };
    void fetchEmails();
  }, []);

  const clearMessages = () => {
    setError(null);
    setSuccessMessage(null);
  };
  const messages = {clear: clearMessages, setError, setSuccess: setSuccessMessage};
  const replaceContact = (updated: ContactEmail) =>
    setContactEmails((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  const verification = useContactCodeVerification({
    requestCode: requestContactEmailVerification,
    verifyCode: verifyContactEmailCode,
    onVerified: (updated: ContactEmail, contactId) =>
      setContactEmails((current) => current.map((item) => (item.id === contactId ? updated : item))),
    verifiedMessage: 'Email verified successfully.',
    errorMessage: getAuthApiErrorMessage,
    messages,
  });
  const primaryVerification = usePrimaryEmailVerification({profile, onProfileUpdate, messages});
  const primaryActions = usePrimaryEmailActions({profile, onProfileUpdate, contactEmails, setContactEmails, messages});

  const hasSecondaryEmail = contactEmails.some((e) => e.email_type === 'secondary');
  const addForm = useAddEmailForm({
    hasSecondaryEmail,
    clearMessages,
    onCreated: (created) => {
      setContactEmails((current) => [created, ...current]);
      verification.begin(created.id);
      setSuccessMessage('Email added. Please enter the verification code sent to your email.');
    },
  });

  const handleContactSubscribeToggle = async (contact: ContactEmail) => {
    clearMessages();
    try {
      replaceContact(await updateContactEmail(contact.id, {subscribe: !contact.subscribe}));
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  const handleContactTypeChange = async (contact: ContactEmail, newType: 'secondary' | 'other') => {
    clearMessages();
    if (newType === 'secondary' && contactEmails.some((e) => e.email_type === 'secondary' && e.id !== contact.id)) {
      setError('You already have a secondary email.');
      return;
    }
    try {
      replaceContact(await updateContactEmail(contact.id, {email_type: newType}));
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  const handleDelete = async (contactId: string) => {
    if (!window.confirm('Are you sure you want to remove this email?')) return;
    clearMessages();
    try {
      await deleteContactEmail(contactId);
      setContactEmails((current) => current.filter((item) => item.id !== contactId));
      verification.forget(contactId);
      setSuccessMessage('Email removed.');
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  return {
    ...addForm,
    contactEmails,
    hasSecondaryEmail,
    error,
    loading,
    successMessage,
    ...connectedEmailVerification(verification),
    ...primaryVerification,
    ...primaryActions,
    clearMessages,
    handleContactSubscribeToggle,
    handleContactTypeChange,
    handleDelete,
  };
};
