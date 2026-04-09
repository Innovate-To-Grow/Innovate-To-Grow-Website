import {useEffect, useState, type FormEvent} from 'react';
import {
  createContactEmail,
  deleteContactEmail,
  getContactEmails,
  getProfile,
  makeContactEmailPrimary,
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
  const [addSubscribe, setAddSubscribe] = useState(true);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);

  // Primary email verification state
  const [primaryVerifying, setPrimaryVerifying] = useState(false);
  const [primaryVerifyCode, setPrimaryVerifyCode] = useState('');
  const [primaryVerifyLoading, setPrimaryVerifyLoading] = useState(false);
  const [primaryVerifyError, setPrimaryVerifyError] = useState<string | null>(null);
  const [primaryResendLoading, setPrimaryResendLoading] = useState(false);
  const [makePrimaryLoadingId, setMakePrimaryLoadingId] = useState<string | null>(null);

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

  const hasSecondaryEmail = contactEmails.some((e) => e.email_type === 'secondary');

  useEffect(() => {
    if (hasSecondaryEmail && addType === 'secondary') {
      setAddType('other');
    }
  }, [hasSecondaryEmail, addType]);

  const handleContactTypeChange = async (contact: ContactEmail, newType: 'secondary' | 'other') => {
    clearMessages();
    if (newType === 'secondary' && contactEmails.some((e) => e.email_type === 'secondary' && e.id !== contact.id)) {
      setError('You already have a secondary email.');
      return;
    }
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
      setAddSubscribe(true);
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
      setSuccessMessage('New code sent. Enter it below and tap Submit code.');
    } catch (err) {
      setVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setResendLoading(false);
    }
  };

  const handleContactRequestVerification = async (contactId: string) => {
    clearMessages();
    setVerifyError(null);
    setVerifyCode('');
    setResendLoading(true);
    try {
      await requestContactEmailVerification(contactId);
      setVerifyingId(contactId);
      setSuccessMessage('Code sent. Enter it below and tap Submit code.');
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    } finally {
      setResendLoading(false);
    }
  };

  const handlePrimaryToggleVerify = async () => {
    if (!profile.primary_email_id) return;
    clearMessages();
    setPrimaryVerifyError(null);
    setPrimaryVerifyCode('');
    setPrimaryResendLoading(true);
    try {
      await requestContactEmailVerification(profile.primary_email_id);
      setPrimaryVerifying(true);
      setSuccessMessage('Verification code sent to your primary email.');
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryResendLoading(false);
    }
  };

  const handlePrimaryVerifySubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!profile.primary_email_id || primaryVerifyCode.length !== 6) return;
    setPrimaryVerifyLoading(true);
    setPrimaryVerifyError(null);
    clearMessages();
    try {
      await verifyContactEmailCode(profile.primary_email_id, primaryVerifyCode);
      setPrimaryVerifying(false);
      setPrimaryVerifyCode('');
      // Refresh profile to pick up the updated verified status
      const updated = await getProfile();
      onProfileUpdate(updated);
      setSuccessMessage('Primary email verified successfully.');
    } catch (err) {
      setPrimaryVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryVerifyLoading(false);
    }
  };

  const handlePrimaryResend = async () => {
    if (!profile.primary_email_id) return;
    setPrimaryResendLoading(true);
    setPrimaryVerifyError(null);
    try {
      await requestContactEmailVerification(profile.primary_email_id);
      setSuccessMessage('Verification code resent.');
    } catch (err) {
      setPrimaryVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryResendLoading(false);
    }
  };

  const handlePrimaryCancelVerify = () => {
    setPrimaryVerifying(false);
    setPrimaryVerifyCode('');
    setPrimaryVerifyError(null);
  };

  const handleMakePrimary = async (contactId: string) => {
    clearMessages();
    setMakePrimaryLoadingId(contactId);
    try {
      await makeContactEmailPrimary(contactId);
      onProfileUpdate(await getProfile());
      setContactEmails(await getContactEmails());
      setSuccessMessage('Primary email updated. Your previous primary address is now listed as a connected email.');
    } catch (err) {
      setError(getAuthApiErrorMessage(err));
    } finally {
      setMakePrimaryLoadingId(null);
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
    hasSecondaryEmail,
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
    primaryVerifying,
    primaryVerifyCode,
    primaryVerifyLoading,
    primaryVerifyError,
    primaryResendLoading,
    makePrimaryLoadingId,
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
    handlePrimaryToggleVerify,
    handlePrimaryVerifySubmit,
    handlePrimaryResend,
    handlePrimaryCancelVerify,
    setPrimaryVerifyCode,
    handleResend,
    handleContactRequestVerification,
    handleVerifySubmit,
    handleMakePrimary,
  };
};
