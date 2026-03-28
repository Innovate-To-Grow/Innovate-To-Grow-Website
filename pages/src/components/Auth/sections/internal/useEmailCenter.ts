import {useEffect, useState, type FormEvent} from 'react';
import {
  createContactEmail,
  deleteContactEmail,
  getContactEmails,
  requestContactEmailVerification,
  updateContactEmail,
  updateProfileFields,
  verifyContactEmailCode,
  type ContactEmail,
  type ProfileResponse,
} from '../../../../services/auth';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

interface UseEmailCenterOptions {
  profile: ProfileResponse;
  onProfileUpdate: (updated: ProfileResponse) => void;
}

export const useEmailCenter = ({profile, onProfileUpdate}: UseEmailCenterOptions) => {
  const [contactEmails, setContactEmails] = useState<ContactEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [subscribeSaving, setSubscribeSaving] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addEmail, setAddEmail] = useState('');
  const [addType, setAddType] = useState<'secondary' | 'other'>('secondary');
  const [addSubscribe, setAddSubscribe] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);

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

  const handlePrimarySubscribeToggle = async () => {
    const newValue = !profile.email_subscribe;
    setSubscribeSaving(true);
    clearMessages();
    try {
      onProfileUpdate(await updateProfileFields({email_subscribe: newValue}));
      setSuccessMessage(`Primary email ${newValue ? 'subscribed' : 'unsubscribed'}.`);
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    } finally {
      setSubscribeSaving(false);
    }
  };

  const handleContactSubscribeToggle = async (contact: ContactEmail) => {
    clearMessages();
    try {
      const updated = await updateContactEmail(contact.id, {subscribe: !contact.subscribe});
      setContactEmails((current) => current.map((item) => (item.id === contact.id ? updated : item)));
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  const handleContactTypeChange = async (contact: ContactEmail, newType: 'secondary' | 'other') => {
    clearMessages();
    try {
      const updated = await updateContactEmail(contact.id, {email_type: newType});
      setContactEmails((current) => current.map((item) => (item.id === contact.id ? updated : item)));
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  const handleAddSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAddLoading(true);
    setAddError(null);
    clearMessages();
    try {
      const created = await createContactEmail({email_address: addEmail.trim(), email_type: addType, subscribe: addSubscribe});
      setContactEmails((current) => [created, ...current]);
      setAddEmail('');
      setAddType('secondary');
      setAddSubscribe(false);
      setShowAddForm(false);
      setVerifyingId(created.id);
      setVerifyCode('');
      setSuccessMessage('Email added. Please enter the verification code sent to your email.');
    } catch (err) {
      setAddError(getAuthApiErrorMessage(err));
    } finally {
      setAddLoading(false);
    }
  };

  const handleVerifySubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!verifyingId || verifyCode.length !== 6) return;
    setVerifyLoading(true);
    setVerifyError(null);
    clearMessages();
    try {
      const updated = await verifyContactEmailCode(verifyingId, verifyCode);
      setContactEmails((current) => current.map((item) => (item.id === verifyingId ? updated : item)));
      setVerifyingId(null);
      setVerifyCode('');
      setSuccessMessage('Email verified successfully.');
    } catch (err) {
      setVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setVerifyLoading(false);
    }
  };

  const handleResend = async (contactId: string) => {
    setResendLoading(true);
    setVerifyError(null);
    try {
      await requestContactEmailVerification(contactId);
      setSuccessMessage('Verification code resent.');
    } catch (err) {
      setVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setResendLoading(false);
    }
  };

  const handleDelete = async (contactId: string) => {
    if (!window.confirm('Are you sure you want to remove this email?')) return;
    clearMessages();
    try {
      await deleteContactEmail(contactId);
      setContactEmails((current) => current.filter((item) => item.id !== contactId));
      if (verifyingId === contactId) {
        setVerifyingId(null);
        setVerifyCode('');
      }
      setSuccessMessage('Email removed.');
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    }
  };

  return {
    addEmail,
    addError,
    addLoading,
    addSubscribe,
    addType,
    contactEmails,
    error,
    loading,
    resendLoading,
    showAddForm,
    subscribeSaving,
    successMessage,
    verifyCode,
    verifyError,
    verifyLoading,
    verifyingId,
    setAddEmail,
    setAddError,
    setAddSubscribe,
    setAddType,
    setShowAddForm,
    setVerifyCode,
    setVerifyError,
    setVerifyingId,
    clearMessages,
    handleAddSubmit,
    handleContactSubscribeToggle,
    handleContactTypeChange,
    handleDelete,
    handlePrimarySubscribeToggle,
    handleResend,
    handleVerifySubmit,
  };
};
