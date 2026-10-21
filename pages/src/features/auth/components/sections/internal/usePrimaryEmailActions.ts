import {useState} from 'react';
import {
  deleteContactEmail,
  getContactEmails,
  getProfile,
  makeContactEmailPrimary,
  updateProfileFields,
  type ContactEmail,
  type ProfileResponse,
} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

interface UsePrimaryEmailActionsOptions {
  profile: ProfileResponse;
  onProfileUpdate: (updated: ProfileResponse) => void;
  contactEmails: ContactEmail[];
  setContactEmails: (emails: ContactEmail[]) => void;
  messages: {clear: () => void; setError: (message: string | null) => void; setSuccess: (message: string) => void};
}

/** What changes which address is primary: its newsletter subscription, promoting another one, removing it. */
export const usePrimaryEmailActions = ({
  profile,
  onProfileUpdate,
  contactEmails,
  setContactEmails,
  messages,
}: UsePrimaryEmailActionsOptions) => {
  const [subscribeSaving, setSubscribeSaving] = useState(false);
  const [makePrimaryLoadingId, setMakePrimaryLoadingId] = useState<string | null>(null);
  const [primaryDeleteLoading, setPrimaryDeleteLoading] = useState(false);

  /** Primary changes move addresses between the profile and the connected list: reload both. */
  const reloadProfileAndEmails = async () => {
    onProfileUpdate(await getProfile());
    setContactEmails(await getContactEmails());
  };

  const handlePrimarySubscribeToggle = async () => {
    const newValue = !profile.email_subscribe;
    setSubscribeSaving(true);
    messages.clear();
    try {
      onProfileUpdate(await updateProfileFields({email_subscribe: newValue}));
      messages.setSuccess(`Primary email ${newValue ? 'subscribed' : 'unsubscribed'}.`);
    } catch (err) {
      messages.setError(getAuthApiErrorMessage(err));
    } finally {
      setSubscribeSaving(false);
    }
  };

  const handleMakePrimary = async (contactId: string) => {
    const contact = contactEmails.find((item) => item.id === contactId);
    const address = contact?.email_address ?? 'this address';
    if (!window.confirm(`Make ${address} your primary email? Your current primary email stays on your account as a connected email.`)) return;
    messages.clear();
    setMakePrimaryLoadingId(contactId);
    try {
      await makeContactEmailPrimary(contactId);
      await reloadProfileAndEmails();
      messages.setSuccess('Primary email updated. Your previous primary address is now listed as a connected email.');
    } catch (err) {
      messages.setError(getAuthApiErrorMessage(err));
    } finally {
      setMakePrimaryLoadingId(null);
    }
  };

  const handlePrimaryDelete = async () => {
    if (!profile.primary_email_id) return;
    if (!window.confirm('Are you sure you want to remove your primary email?')) return;
    messages.clear();
    setPrimaryDeleteLoading(true);
    try {
      await deleteContactEmail(profile.primary_email_id);
      // The backend promotes another email to primary (or leaves none for a
      // phone-only account), so refresh both the profile and the connected list.
      await reloadProfileAndEmails();
      messages.setSuccess('Email removed.');
    } catch (err) {
      // Backend returns a 409 with an actionable message when this would remove
      // the member's last verified recovery contact.
      messages.setError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryDeleteLoading(false);
    }
  };

  return {
    subscribeSaving,
    makePrimaryLoadingId,
    primaryDeleteLoading,
    handlePrimarySubscribeToggle,
    handleMakePrimary,
    handlePrimaryDelete,
  };
};
