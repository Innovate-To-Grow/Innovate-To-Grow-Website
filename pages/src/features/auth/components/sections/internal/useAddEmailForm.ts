import {useState, type FormEvent} from 'react';
import {createContactEmail, type ContactEmail} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

type ContactEmailType = 'secondary' | 'other';

interface UseAddEmailFormOptions {
  hasSecondaryEmail: boolean;
  clearMessages: () => void;
  /** The new address was created: list it and start its verification. */
  onCreated: (created: ContactEmail) => void;
}

/** The "add an email address" form: its fields, and creating the address. */
export const useAddEmailForm = ({hasSecondaryEmail, clearMessages, onCreated}: UseAddEmailFormOptions) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [addEmail, setAddEmail] = useState('');
  const [addType, setAddType] = useState<ContactEmailType>('secondary');
  const [addSubscribe, setAddSubscribe] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Derive the effective add type during render instead of correcting it in an effect:
  // when a secondary email already exists, a 'secondary' selection is coerced to 'other'.
  // The 'secondary' <option> is disabled in that state, so this only ever fixes up the
  // default/reset value, never a user choice.
  const effectiveAddType: ContactEmailType = hasSecondaryEmail && addType === 'secondary' ? 'other' : addType;

  const handleAddSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAddLoading(true);
    setAddError(null);
    clearMessages();
    try {
      const created = await createContactEmail({email_address: addEmail.trim(), email_type: effectiveAddType, subscribe: addSubscribe});
      setAddEmail('');
      setAddType('secondary');
      setAddSubscribe(false);
      setShowAddForm(false);
      onCreated(created);
    } catch (err) {
      setAddError(getAuthApiErrorMessage(err));
    } finally {
      setAddLoading(false);
    }
  };

  return {
    addEmail,
    addError,
    addLoading,
    addSubscribe,
    addType: effectiveAddType,
    showAddForm,
    setAddEmail,
    setAddError,
    setAddSubscribe,
    setAddType,
    setShowAddForm,
    handleAddSubmit,
  };
};
